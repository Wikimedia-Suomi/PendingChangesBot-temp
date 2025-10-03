const { createApp, reactive, computed, onMounted, watch } = Vue;

function parseTextarea(value) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function formatDateTime(value) {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

createApp({
  setup() {
    const initialElement = document.getElementById("initial-wikis");
    const initialData = initialElement ? JSON.parse(initialElement.textContent) : [];

    const configurationStorageKey = "configurationOpen";
    const selectedWikiStorageKey = "selectedWikiId";
    const sortOrderStorageKey = "pendingSortOrder";
    const pageDisplayLimit = 10;

    function loadFromStorage(key) {
      if (typeof window === "undefined") {
        return null;
      }
      try {
        return window.localStorage.getItem(key);
      } catch (error) {
        return null;
      }
    }

    function saveToStorage(key, value) {
      if (typeof window === "undefined") {
        return;
      }
      try {
        if (value === null || typeof value === "undefined") {
          window.localStorage.removeItem(key);
        } else {
          window.localStorage.setItem(key, String(value));
        }
      } catch (error) {
        // Ignore storage errors.
      }
    }

    function loadConfigurationOpen() {
      return loadFromStorage(configurationStorageKey) === "true";
    }

    function persistConfigurationOpen(value) {
      saveToStorage(configurationStorageKey, value ? "true" : "false");
    }

    function loadSelectedWikiId(wikis) {
      if (!Array.isArray(wikis) || !wikis.length) {
        return "";
      }
      const storedValue = loadFromStorage(selectedWikiStorageKey);
      if (storedValue === null) {
        return wikis[0].id;
      }
      const parsedValue = Number(storedValue);
      if (!Number.isNaN(parsedValue)) {
        const matchedWiki = wikis.find((wiki) => wiki.id === parsedValue || Number(wiki.id) === parsedValue);
        if (matchedWiki) {
          return matchedWiki.id;
        }
      }
      return wikis[0].id;
    }

    function persistSelectedWikiId(value) {
      if (value === "") {
        saveToStorage(selectedWikiStorageKey, null);
        return;
      }
      saveToStorage(selectedWikiStorageKey, value);
    }

    function loadSortOrder() {
      const storedValue = loadFromStorage(sortOrderStorageKey);
      if (storedValue === "newest" || storedValue === "oldest" || storedValue === "random") {
        return storedValue;
      }
      return "newest";
    }

    function persistSortOrder(value) {
      saveToStorage(sortOrderStorageKey, value);
    }

    function getPendingTimestamp(page) {
      if (!page || !page.pending_since) {
        return 0;
      }
      const timestamp = new Date(page.pending_since).getTime();
      return Number.isNaN(timestamp) ? 0 : timestamp;
    }

    function shufflePages(pages) {
      const shuffled = [...pages];
      for (let index = shuffled.length - 1; index > 0; index -= 1) {
        const swapIndex = Math.floor(Math.random() * (index + 1));
        [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
      }
      return shuffled;
    }

    function sortPages(pages, order) {
      if (!Array.isArray(pages)) {
        return [];
      }
      if (order === "random") {
        return shufflePages(pages);
      }
      const sorted = [...pages];
      sorted.sort((first, second) => {
        const firstTimestamp = getPendingTimestamp(first);
        const secondTimestamp = getPendingTimestamp(second);
        if (order === "oldest") {
          return firstTimestamp - secondTimestamp;
        }
        return secondTimestamp - firstTimestamp;
      });
      return sorted;
    }

    const state = reactive({
      wikis: initialData,
      selectedWikiId: initialData.length ? loadSelectedWikiId(initialData) : "",
      sortOrder: loadSortOrder(),
      pages: [],
      loading: false,
      error: "",
      configurationOpen: loadConfigurationOpen(),
    });

    const forms = reactive({
      blockingCategories: "",
      autoApprovedGroups: "",
    });

    const currentWiki = computed(() =>
      state.wikis.find((wiki) => wiki.id === state.selectedWikiId) || null,
    );

    const visiblePages = computed(() => state.pages.slice(0, pageDisplayLimit));

    const hasMorePages = computed(() => state.pages.length > pageDisplayLimit);

    function syncForms() {
      if (!currentWiki.value) {
        forms.blockingCategories = "";
        forms.autoApprovedGroups = "";
        return;
      }
      forms.blockingCategories = (currentWiki.value.configuration.blocking_categories || []).join("\n");
      forms.autoApprovedGroups = (currentWiki.value.configuration.auto_approved_groups || []).join("\n");
    }

    async function apiRequest(url, options = {}) {
      state.error = "";
      try {
        const response = await fetch(url, options);
        if (!response.ok) {
          let message = response.statusText;
          try {
            const data = await response.json();
            if (data && data.error) {
              message = data.error;
            }
          } catch (error) {
            // Ignore JSON parsing errors.
          }
          throw new Error(message || "Unknown error");
        }
        return response.json();
      } catch (error) {
        state.error = error.message || "Request failed";
        throw error;
      }
    }

    async function fetchRevisionsForPage(wikiId, pageId) {
      try {
        const data = await apiRequest(`/api/wikis/${wikiId}/pages/${pageId}/revisions/`);
        return data.revisions || [];
      } catch (error) {
        return [];
      }
    }

    async function loadPending() {
      if (!state.selectedWikiId) {
        state.pages = [];
        return;
      }
      state.loading = true;
      try {
        const wikiId = state.selectedWikiId;
        const data = await apiRequest(`/api/wikis/${wikiId}/pending/`);
        const pagesWithRevisions = await Promise.all(
          (data.pages || []).map(async (page) => {
            let revisions = Array.isArray(page.revisions) ? page.revisions : [];
            if (!revisions.length) {
              revisions = await fetchRevisionsForPage(wikiId, page.pageid);
            }
            return {
              ...page,
              revisions,
            };
          }),
        );
        if (wikiId === state.selectedWikiId) {
          state.pages = sortPages(pagesWithRevisions, state.sortOrder);
        }
      } catch (error) {
        state.pages = [];
      } finally {
        state.loading = false;
      }
    }

    async function refresh() {
      if (!state.selectedWikiId) {
        return;
      }
      state.loading = true;
      try {
        await apiRequest(`/api/wikis/${state.selectedWikiId}/refresh/`, {
          method: "POST",
        });
        await loadPending();
      } finally {
        state.loading = false;
      }
    }

    async function clearCache() {
      if (!state.selectedWikiId) {
        return;
      }
      state.loading = true;
      try {
        await apiRequest(`/api/wikis/${state.selectedWikiId}/clear/`, {
          method: "POST",
        });
        state.pages = [];
      } finally {
        state.loading = false;
      }
    }

    async function saveConfiguration() {
      if (!state.selectedWikiId) {
        return;
      }
      const payload = {
        blocking_categories: parseTextarea(forms.blockingCategories),
        auto_approved_groups: parseTextarea(forms.autoApprovedGroups),
      };
      try {
        const data = await apiRequest(`/api/wikis/${state.selectedWikiId}/configuration/`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });
        const wikiIndex = state.wikis.findIndex((wiki) => wiki.id === state.selectedWikiId);
        if (wikiIndex >= 0) {
          state.wikis[wikiIndex].configuration = data;
        }
        syncForms();
      } catch (error) {
        // Error already handled in apiRequest.
      }
    }

    function formatDate(value) {
      return formatDateTime(value);
    }

    function formatTitle(title) {
      if (!title) {
        return "";
      }
      return title.replace(/_/g, " ");
    }

    function buildLatestRevisionUrl(page) {
      if (!page || !page.title) {
        return "";
      }
      const wiki = currentWiki.value;
      if (!wiki || !wiki.api_endpoint) {
        return "";
      }
      const normalizedTitle = page.title.replace(/ /g, "_");
      const encodedTitle = encodeURIComponent(normalizedTitle);
      try {
        const apiUrl = new URL(wiki.api_endpoint);
        return `${apiUrl.origin}/wiki/${encodedTitle}`;
      } catch (error) {
        return `/wiki/${encodedTitle}`;
      }
    }

    function toggleConfiguration() {
      state.configurationOpen = !state.configurationOpen;
    }

    watch(
      () => state.configurationOpen,
      (newValue) => {
        persistConfigurationOpen(newValue);
      },
      { immediate: true },
    );

    watch(
      () => state.selectedWikiId,
      (newValue) => {
        persistSelectedWikiId(newValue);
      },
      { immediate: true },
    );

    watch(
      () => state.sortOrder,
      (newValue) => {
        state.pages = sortPages(state.pages, newValue);
        persistSortOrder(newValue);
      },
      { immediate: true },
    );

    watch(currentWiki, () => {
      syncForms();
      loadPending();
    }, { immediate: true });

    onMounted(() => {
      syncForms();
    });

    return {
      state,
      forms,
      currentWiki,
      visiblePages,
      hasMorePages,
      pageDisplayLimit,
      refresh,
      clearCache,
      saveConfiguration,
      loadPending,
      formatDate,
      toggleConfiguration,
      formatTitle,
      buildLatestRevisionUrl,
    };
  },
}).mount("#app");
