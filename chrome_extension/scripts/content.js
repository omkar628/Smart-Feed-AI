console.log("SmartFeed AI: Content script active. Initializing observer...");

let processTimer = null;

const DEBOUNCE_DELAY = 1000;
const AI_CARD_STYLE_ID = "smartfeed-ai-card-style";

const REMOVE_ANIMATION_DURATION = 350;
const FLIP_ANIMATION_DURATION = 500;


injectSmartFeedStyles();



// ============================================================
// EXTRACT VIDEOS FROM YOUTUBE
// ============================================================

function extractAndProcessVideos() {

    const videoElements = document.querySelectorAll(

        'ytd-rich-item-renderer:not([data-ai-processed="true"])'

    );


    if (videoElements.length === 0) return;


    console.log(

        `Found ${videoElements.length} new video cards.`

    );


    const videoBatch = [];

    const elementMap = new Map();



    videoElements.forEach((element) => {

        try {


            // ====================================================
            // 1. FIND REAL VIDEO TITLE LINK
            // ====================================================

            const titleLink = element.querySelector(

                'a.ytLockupMetadataViewModelTitle[href*="/watch?v="]'

            );


            if (!titleLink) {

                console.warn(

                    "Skipped card: Real title link not found."

                );

                return;

            }



            // ====================================================
            // 2. EXTRACT VIDEO ID
            // ====================================================

            const url = new URL(titleLink.href);


            const videoId = url.searchParams.get("v");


            if (!videoId) {

                console.warn(

                    "Skipped card: Video ID not found."

                );

                return;

            }



            // ====================================================
            // 3. EXTRACT REAL VIDEO TITLE
            // ====================================================

            const title = titleLink.textContent.trim();


            if (!title) {

                console.warn(

                    "Skipped card: Video title is empty."

                );

                return;

            }



            // ====================================================
            // 4. EXTRACT CHANNEL / METADATA
            // ====================================================

            const metadataRows = element.querySelectorAll(

                ".ytContentMetadataViewModelMetadataRow"

            );


            let channel = "Unknown Channel";


            if (metadataRows.length > 0) {

                channel = metadataRows[0]
                    .textContent
                    .trim();

            }



            // ====================================================
            // 5. DEBUG LOG
            // ====================================================

            console.log(

                "EXTRACTED VIDEO:",

                {

                    videoId,

                    title,

                    channel

                }

            );



            // ====================================================
            // 6. ADD VIDEO TO BATCH
            // ====================================================

            videoBatch.push({

                video_id: videoId,

                title: title,

                channel: channel,

                description: ""

            });



            // ====================================================
            // 7. CONNECT VIDEO ID TO YOUTUBE ELEMENT
            // ====================================================

            elementMap.set(

                videoId,

                element

            );



            // ====================================================
            // 8. MARK VIDEO AS PROCESSED
            // ====================================================

            element.setAttribute(

                "data-ai-processed",

                "true"

            );


        }

        catch (error) {

            console.error(

                "Video extraction error:",

                error

            );

        }

    });



    console.log(

        `Successfully extracted ${videoBatch.length} videos. Sending to AI...`

    );



    if (videoBatch.length > 0) {

        sendToAIBackend(

            videoBatch,

            elementMap

        );

    }

}



// ============================================================
// SEND VIDEOS TO BACKGROUND SERVICE WORKER
// ============================================================

function sendToAIBackend(

    videos,

    elementMap

) {


    chrome.storage.local.get(

        ["userInterests"],

        (result) => {


            const interests = result.userInterests;



            if (

                !interests ||

                Object.keys(interests).length === 0

            ) {


                console.warn(

                    "No interests saved. Open the extension and save your interests."

                );


                return;

            }



            console.log(

                "Sending videos to background...",

                {

                    interests,

                    videoCount: videos.length

                }

            );



            chrome.runtime.sendMessage(

                {

                    action: "analyzeFeed",

                    interests: interests,

                    videos: videos

                },


                (response) => {


                    // ============================================
                    // COMMUNICATION ERROR
                    // ============================================

                    if (chrome.runtime.lastError) {


                        console.error(

                            "Communication error:",

                            chrome.runtime.lastError

                        );


                        return;

                    }



                    // ============================================
                    // SUCCESS
                    // ============================================

                    if (response?.success) {


                        console.log(

                            `Received AI rankings for ${response.data.length} videos.`

                        );


                        applyFiltersToDOM(

                            response.data,

                            elementMap

                        );

                    }


                    // ============================================
                    // BACKEND ERROR
                    // ============================================

                    else {


                        console.error(

                            "Backend error:",

                            response

                        );

                    }

                }

            );

        }

    );

}



// ============================================================
// GET ALL CURRENT VIDEO CARDS
// ============================================================

function getCurrentVideoCards() {

    return Array.from(

        document.querySelectorAll(

            'ytd-rich-item-renderer[data-ai-processed="true"]'

        )

    );

}



// ============================================================
// FLIP STEP 1
//
// RECORD CURRENT CARD POSITIONS
// ============================================================

function recordCardPositions(cards) {

    const positions = new Map();


    cards.forEach((card) => {


        if (!card.isConnected) return;


        const rectangle = card.getBoundingClientRect();


        positions.set(

            card,

            {

                left: rectangle.left,

                top: rectangle.top

            }

        );

    });


    return positions;

}



// ============================================================
// FLIP STEP 2
//
// ANIMATE CARDS FROM OLD POSITION TO NEW POSITION
// ============================================================

function animateCardRearrangement(

    oldPositions,

    remainingCards

) {


    remainingCards.forEach((card) => {


        if (!card.isConnected) return;


        const oldPosition = oldPositions.get(card);


        if (!oldPosition) return;



        // ====================================================
        // GET NEW POSITION
        // ====================================================

        const newRectangle = card.getBoundingClientRect();



        // ====================================================
        // CALCULATE MOVEMENT DIFFERENCE
        // ====================================================

        const deltaX =

            oldPosition.left -

            newRectangle.left;


        const deltaY =

            oldPosition.top -

            newRectangle.top;



        // ====================================================
        // CARD DID NOT MOVE
        // ====================================================

        if (

            Math.abs(deltaX) < 1 &&

            Math.abs(deltaY) < 1

        ) {

            return;

        }



        // ====================================================
        // INVERT
        //
        // Move the card visually back to its old position.
        // ====================================================

        card.style.transition = "none";


        card.style.transform =

            `translate(${deltaX}px, ${deltaY}px)`;



        // ====================================================
        // FORCE BROWSER REFLOW
        // ====================================================

        card.getBoundingClientRect();



        // ====================================================
        // PLAY
        //
        // Animate transform back to zero.
        // ====================================================

        requestAnimationFrame(() => {


            card.style.transition =

                `transform ${FLIP_ANIMATION_DURATION}ms cubic-bezier(0.22, 1, 0.36, 1)`;


            card.style.transform =

                "translate(0px, 0px)";



            // =================================================
            // CLEAN INLINE STYLES AFTER ANIMATION
            // =================================================

            setTimeout(() => {


                if (!card.isConnected) return;


                card.style.transition = "";

                card.style.transform = "";


            }, FLIP_ANIMATION_DURATION);

        });

    });

}



// ============================================================
// APPLY AI RESULTS TO YOUTUBE
// ============================================================

function applyFiltersToDOM(

    rankedVideos,

    elementMap

) {


    console.log(

        "Applying AI filtering with FLIP animation..."

    );



    // ========================================================
    // FIND ALL CARDS THAT WILL BE REMOVED
    // ========================================================

    const cardsToRemove = [];


    rankedVideos.forEach((video) => {


        if (video.action !== "Hide") return;


        const element =

            elementMap.get(video.video_id);


        if (!element) return;


        if (!element.isConnected) return;


        cardsToRemove.push(

            {

                video: video,

                element: element

            }

        );

    });



    // ========================================================
    // RECORD POSITIONS BEFORE REMOVAL
    //
    // FLIP:
    // FIRST
    // ========================================================

    const currentCards = getCurrentVideoCards();


    const oldPositions = recordCardPositions(

        currentCards

    );



    // ========================================================
    // ADD BADGES TO ACCEPTED VIDEOS
    // ========================================================

    rankedVideos.forEach((video) => {


        if (video.action === "Hide") return;


        const element =

            elementMap.get(video.video_id);


        if (!element) return;


        if (!element.isConnected) return;



        const confidence =

            (video.confidence * 100)

                .toFixed(1);



        // ====================================================
        // REMOVE OLD BADGE
        // ====================================================

        const oldBadge = element.querySelector(

            ".smartfeed-ai-badge"

        );


        if (oldBadge) {

            oldBadge.remove();

        }



        // ====================================================
        // CREATE BADGE
        // ====================================================

        const badge =

            document.createElement("div");


        badge.className =

            "smartfeed-ai-badge";


        badge.textContent =

            `${video.topic} match ${confidence}%`;



        // ====================================================
        // ADD MATCH STYLING
        // ====================================================

        element.classList.add(

            "smartfeed-ai-match"

        );


        element.style.opacity = "1";

        element.style.pointerEvents = "auto";


        element.title =

            `AI Match: ${video.topic} (${confidence}%)`;


        element.prepend(

            badge

        );

    });



    // ========================================================
    // NO CARDS NEED REMOVAL
    // ========================================================

    if (cardsToRemove.length === 0) {

        console.log(

            "No videos need to be removed."

        );

        return;

    }



    // ========================================================
    // START REMOVAL ANIMATION
    // ========================================================

    cardsToRemove.forEach((item) => {


        console.log(

            `Animating removal: ${item.video.title}`

        );


        item.element.classList.add(

            "smartfeed-ai-removing"

        );

    });



    // ========================================================
    // WAIT FOR FADE ANIMATION
    // ========================================================

    setTimeout(() => {


        // ====================================================
        // REMOVE REJECTED CARDS
        //
        // FLIP:
        // LAST
        // ====================================================

        cardsToRemove.forEach((item) => {


            if (item.element.isConnected) {


                item.element.remove();


                console.log(

                    `Removed video: ${item.video.title}`

                );

            }

        });



        // ====================================================
        // WAIT FOR YOUTUBE / BROWSER LAYOUT
        // ====================================================

        requestAnimationFrame(() => {


            requestAnimationFrame(() => {


                // ============================================
                // GET REMAINING CARDS
                // ============================================

                const remainingCards =

                    getCurrentVideoCards();



                // ============================================
                // RUN FLIP ANIMATION
                // ============================================

                animateCardRearrangement(

                    oldPositions,

                    remainingCards

                );

            });

        });


    }, REMOVE_ANIMATION_DURATION);

}



// ============================================================
// ADD SMARTFEED CSS
// ============================================================

function injectSmartFeedStyles() {


    if (

        document.getElementById(

            AI_CARD_STYLE_ID

        )

    ) {

        return;

    }



    const style =

        document.createElement("style");


    style.id =

        AI_CARD_STYLE_ID;



    style.textContent = `


        /* ================================================
           AI MATCHED VIDEO
        ================================================= */


        ytd-rich-item-renderer.smartfeed-ai-match {

            position: relative;

            border-radius: 18px;

            box-shadow:
                0 18px 40px
                rgba(14, 165, 233, 0.16);

            outline:
                2px solid
                rgba(103, 232, 249, 0.7);

            outline-offset: 3px;

            background:
                linear-gradient(
                    180deg,
                    rgba(103, 232, 249, 0.08),
                    rgba(15, 23, 42, 0.02)
                );

        }



        /* ================================================
           AI MATCHED VIDEO HOVER
        ================================================= */


        ytd-rich-item-renderer.smartfeed-ai-match:hover {

            transform:

                translateY(-2px);

            box-shadow:

                0 24px 44px

                rgba(14, 165, 233, 0.22);

        }



        /* ================================================
           VIDEO REMOVAL ANIMATION
        ================================================= */


        ytd-rich-item-renderer.smartfeed-ai-removing {

            opacity: 0 !important;

            transform:

                scale(0.82)

                translateY(20px) !important;

            filter:

                blur(5px)

                grayscale(0.9);

            pointer-events:

                none;

            transition:

                opacity ${REMOVE_ANIMATION_DURATION}ms ease,

                transform ${REMOVE_ANIMATION_DURATION}ms ease,

                filter ${REMOVE_ANIMATION_DURATION}ms ease;

        }



        /* ================================================
           AI MATCH BADGE
        ================================================= */


        .smartfeed-ai-badge {

            margin:

                0 0 10px;

            display:

                inline-flex;

            align-items:

                center;

            padding:

                7px 12px;

            border-radius:

                999px;

            font-size:

                11px;

            font-weight:

                700;

            letter-spacing:

                0.04em;

            text-transform:

                uppercase;

            color:

                #dffbff;

            background:

                linear-gradient(

                    135deg,

                    rgba(8, 145, 178, 0.92),

                    rgba(14, 116, 144, 0.92)

                );

            box-shadow:

                0 10px 24px

                rgba(8, 145, 178, 0.28);

            width:

                fit-content;

        }


    `;



    document.head.appendChild(

        style

    );

}



// ============================================================
// WATCH YOUTUBE FOR NEW VIDEOS
// ============================================================

const observer =

    new MutationObserver(() => {


        clearTimeout(

            processTimer

        );



        processTimer =

            setTimeout(() => {


                if (

                    window.location.pathname === "/"

                ) {


                    extractAndProcessVideos();

                }


            }, DEBOUNCE_DELAY);

    });



observer.observe(

    document.body,

    {

        childList: true,

        subtree: true

    }

);



// ============================================================
// INITIAL SCAN
// ============================================================

setTimeout(

    extractAndProcessVideos,

    2000

);