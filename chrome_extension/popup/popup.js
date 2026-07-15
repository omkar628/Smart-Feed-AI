document.addEventListener("DOMContentLoaded", () => {
    const body = document.body;
    const saveBtn = document.getElementById("save-btn");
    const addTopicBtn = document.getElementById("add-topic-btn");
    const themeToggleInput = document.getElementById("theme-toggle-input");
    const topicsContainer = document.getElementById("topics-container");
    const topicTemplate = document.getElementById("topic-row-template");
    const allocationSummary = document.getElementById("allocation-summary");
    const allocationTotal = document.getElementById("allocation-total");
    const allocationBar = document.getElementById("allocation-bar");
    const allocationHint = document.getElementById("allocation-hint");
    const statusMsg = document.getElementById("status");
    const THEME_STORAGE_KEY = "popupTheme";
    const THEME_DEEP_FOCUS = "deep-focus";
    const THEME_ZEN_SPACE = "zen-space";

    const defaultTopics = [
        { topic: "JEE Advanced", weight: 50 },
        { topic: "Programming", weight: 30 },
        { topic: "Artificial Intelligence", weight: 20 }
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

    function updateAllocationSummary() {
        const rows = getRows();
        const total = rows.reduce((sum, row) => {
            const value = parseInt(row.querySelector(".topic-weight").value, 10);
            return sum + (Number.isNaN(value) ? 0 : value);
        }, 0);

        const clampedTotal = Math.max(0, Math.min(total, 100));
        allocationTotal.textContent = `${total}%`;
        allocationBar.style.width = `${clampedTotal}%`;
        saveBtn.disabled = total !== 100;

        if (total === 100) {
            allocationSummary.dataset.state = "valid";
            allocationHint.textContent = "Perfect balance. Your feed is ready to save.";
        } else if (total < 100) {
            allocationSummary.dataset.state = "under";
            allocationHint.textContent = `${100 - total}% left to assign.`;
        } else {
            allocationSummary.dataset.state = "over";
            allocationHint.textContent = `${total - 100}% over the limit. Reduce a few shares.`;
        }
    }

    function addTopicRow(topic = "", weight = "") {
        const row = topicTemplate.content.firstElementChild.cloneNode(true);
        const topicInput = row.querySelector(".topic-name");
        const weightInput = row.querySelector(".topic-weight");
        const removeBtn = row.querySelector(".remove-topic-btn");

        topicInput.value = topic;
        weightInput.value = weight;

        const syncSummary = () => {
            updateAllocationSummary();
            if (statusMsg.textContent) {
                setStatus("");
            }
        };

        topicInput.addEventListener("input", syncSummary);
        weightInput.addEventListener("input", syncSummary);

        removeBtn.addEventListener("click", () => {
            row.remove();
            updateAllocationSummary();
            if (getRows().length === 0) {
                addTopicRow();
            }
        });

        topicsContainer.appendChild(row);
        updateAllocationSummary();
    }

    function hydrateTopics(topicEntries) {
        topicsContainer.innerHTML = "";
        topicEntries.forEach(({ topic, weight }) => addTopicRow(topic, weight));

        if (topicEntries.length === 0) {
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
        const interests = {};
        let totalWeight = 0;

        for (const row of rows) {
            const topic = row.querySelector(".topic-name").value.trim();
            const weight = parseInt(row.querySelector(".topic-weight").value, 10) || 0;

            if (!topic && weight === 0) {
                continue;
            }

            if (!topic) {
                setStatus("Every non-zero share needs a topic name.", "error");
                return;
            }

            if (weight <= 0) {
                setStatus(`"${topic}" needs a percentage greater than 0.`, "error");
                return;
            }

            interests[topic] = weight;
            totalWeight += weight;
        }

        if (Object.keys(interests).length === 0) {
            setStatus("Add at least one topic before saving.", "error");
            return;
        }

        if (totalWeight !== 100) {
            setStatus(`Your total must be 100%. It is currently ${totalWeight}%.`, "error");
            return;
        }

        chrome.storage.local.set({ userInterests: interests }, () => {
            setStatus("Preferences saved. Refresh YouTube to apply the new mix.", "success");
        });
    });

    chrome.storage.local.get(["userInterests", THEME_STORAGE_KEY], (result) => {
        applyTheme(result[THEME_STORAGE_KEY]);

        const savedInterests = result.userInterests
            ? Object.entries(result.userInterests).map(([topic, weight]) => ({ topic, weight }))
            : defaultTopics;

        hydrateTopics(savedInterests);
        setStatus("Your saved mix appears here each time you open the extension.");
    });
});
