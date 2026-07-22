document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const saveBtn = document.getElementById("save-btn");
    const addTopicBtn = document.getElementById("add-topic-btn");
    const themeToggleInput = document.getElementById("theme-toggle-input");
    const topicsContainer = document.getElementById("topics-container");
    const topicTemplate = document.getElementById("topic-row-template");
    const statusMsg = document.getElementById("status");
    const THEME_STORAGE_KEY = "popupTheme";
    const THEME_DEEP_FOCUS = "deep-focus";
    const THEME_ZEN_SPACE = "zen-space";

    const defaultTopics = [
        "JEE Advanced",
        "Programming",
        "Artificial Intelligence"
    ];

    function setStatus(message, type = "") {
        statusMsg.textContent = message;
        statusMsg.className = "status-message";

        if (message) {
            statusMsg.classList.add("visible");
        }

        if (type && message) {
            statusMsg.classList.add(type);
        }
    }

    function applyTheme(themeName) {
        const theme = themeName === THEME_ZEN_SPACE
            ? THEME_ZEN_SPACE
            : THEME_DEEP_FOCUS;

        body.dataset.theme = theme;
        themeToggleInput.checked = theme === THEME_ZEN_SPACE;
    }

    function getRows() {
        return Array.from(topicsContainer.querySelectorAll(".topic-row"));
    }

    function addTopicRow(topic = "") {
        const row = topicTemplate.content.firstElementChild.cloneNode(true);
        const topicInput = row.querySelector(".topic-name");
        const removeBtn = row.querySelector(".remove-topic-btn");

        topicInput.value = topic;

        topicInput.addEventListener("input", () => {
            if (statusMsg.textContent) {
                setStatus("");
            }
        });

        removeBtn.addEventListener("click", () => {
            row.remove();
            if (getRows().length === 0) {
                addTopicRow();
            }
        });

        topicsContainer.appendChild(row);
    }

    function hydrateTopics(topics) {
        topicsContainer.innerHTML = "";
        topics.forEach((topic) => addTopicRow(topic));

        if (topics.length === 0) {
            addTopicRow();
        }
    }

    addTopicBtn.addEventListener("click", () => addTopicRow());
    themeToggleInput.addEventListener("change", () => {
        const nextTheme = themeToggleInput.checked
            ? THEME_ZEN_SPACE
            : THEME_DEEP_FOCUS;

        applyTheme(nextTheme);
        chrome.storage.local.set({ [THEME_STORAGE_KEY]: nextTheme });
    });

    saveBtn.addEventListener("click", () => {
        const rows = getRows();
        const selectedTopics = [];
        const seenTopics = new Set();

        for (const row of rows) {
            const topic = row.querySelector(".topic-name").value.trim();

            if (!topic) {
                continue;
            }

            const topicKey = topic.toLocaleLowerCase();
            if (!seenTopics.has(topicKey)) {
                selectedTopics.push(topic);
                seenTopics.add(topicKey);
            }
        }

        if (selectedTopics.length === 0) {
            setStatus("Add at least one topic before saving.", "error");
            return;
        }

        chrome.storage.local.set({ userInterests: selectedTopics }, () => {
            setStatus("Preferences saved. Refresh YouTube to apply semantic ranking.", "success");
        });
    });

    chrome.storage.local.get(["userInterests", THEME_STORAGE_KEY], (result) => {
        applyTheme(result[THEME_STORAGE_KEY]);

        const savedTopics = Array.isArray(result.userInterests)
            ? result.userInterests
            : result.userInterests
                ? Object.keys(result.userInterests)
            : defaultTopics;

        hydrateTopics(savedTopics);
        setStatus("Your selected topics appear here each time you open the extension.");
    });
});
