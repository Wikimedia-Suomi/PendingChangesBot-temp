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

    const state = reactive({
      wikis: initialData,
      selectedWikiId: initialData.length ? initialData[0].id : "",
      pages: [],
      loading: false,
      error: "",
      configurationOpen: true,
    });

    const forms = reactive({
      blockingCategories: "",
      autoApprovedGroups: "",
    });

    const currentWiki = computed(() =>
      state.wikis.find((wiki) => wiki.id === state.selectedWikiId) || null,
    );

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

    async function loadPending() {
      if (!state.selectedWikiId) {
        state.pages = [];
        return;
      }
      state.loading = true;
      try {
        const data = await apiRequest(`/api/wikis/${state.selectedWikiId}/pending/`);
        state.pages = data.pages;
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

    function toggleConfiguration() {
      state.configurationOpen = !state.configurationOpen;
    }

    watch(currentWiki, () => {
      syncForms();
      loadPending();
      state.configurationOpen = true;
    }, { immediate: true });

    onMounted(() => {
      syncForms();
    });

    return {
      state,
      forms,
      currentWiki,
      refresh,
      clearCache,
      saveConfiguration,
      loadPending,
      formatDate,
      toggleConfiguration,
    };
  },
}).mount("#app");
