/**
 * GLOBAL WEALTH – Scene 1 Cinematic Scroll-Driven Engine
 * Powered by HTML5 Canvas + GSAP ScrollTrigger
 * 
 * Features:
 * - 95-frame responsive Canvas renderer with aspect-ratio preservation
 * - Non-blocking progressive image preloader with instant first-frame paint
 * - Bidirectional scrub (forwards and backwards)
 * - Independent GSAP timeline for typography and headlines
 * - Resilient fallback to nearest loaded frame on rapid scroll
 */

(function () {
    "use strict";

    const TOTAL_FRAMES = 95;
    const FRAME_DIR = "/static/frames/scene1";
    
    // Format frame filename: "frame 1.jpg" ... "frame 95.jpg"
    function getFrameUrl(index) {
        return `${FRAME_DIR}/frame ${index}.jpg`;
    }

    document.addEventListener("DOMContentLoaded", function () {
        const container = document.getElementById("globalWealthScene1");
        const canvas = document.getElementById("scene1Canvas");
        const overlay = document.querySelector(".scene1-overlay");
        const progressBar = document.querySelector(".scene1-progress-bar");
        const loaderHud = document.querySelector(".scene1-loader-hud");

        if (!container || !canvas) {
            return;
        }

        const ctx = canvas.getContext("2d", { alpha: false });
        if (!ctx) return;

        // Internal rendering state
        const frames = new Array(TOTAL_FRAMES + 1);
        let loadedCount = 0;
        let currentRenderedIndex = -1;

        // Resize canvas to match container / device pixel ratio
        function resizeCanvas() {
            const rect = canvas.getBoundingClientRect();
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            const w = Math.round(rect.width * dpr);
            const h = Math.round(rect.height * dpr);

            if (canvas.width !== w || canvas.height !== h) {
                canvas.width = w;
                canvas.height = h;
                if (currentRenderedIndex > 0) {
                    renderFrame(currentRenderedIndex);
                }
            }
        }

        // Draw image keeping cover aspect ratio
        function drawCover(img) {
            if (!img || !img.complete || !img.naturalWidth) return;
            const cw = canvas.width;
            const ch = canvas.height;
            const iw = img.naturalWidth;
            const ih = img.naturalHeight;

            const scale = Math.max(cw / iw, ch / ih);
            const dw = iw * scale;
            const dh = ih * scale;
            const dx = (cw - dw) * 0.5;
            const dy = (ch - dh) * 0.5;

            ctx.drawImage(img, 0, 0, iw, ih, dx, dy, dw, dh);
        }

        // Retrieve best available frame to prevent any visual blanking during fast scrolling
        function getBestAvailableFrame(index) {
            if (frames[index] && frames[index].isLoaded) {
                return frames[index];
            }
            // Scan nearby frames
            for (let offset = 1; offset < TOTAL_FRAMES; offset++) {
                const prev = index - offset;
                if (prev >= 1 && frames[prev] && frames[prev].isLoaded) {
                    return frames[prev];
                }
                const next = index + offset;
                if (next <= TOTAL_FRAMES && frames[next] && frames[next].isLoaded) {
                    return frames[next];
                }
            }
            return (frames[1] && frames[1].isLoaded) ? frames[1] : null;
        }

        function renderFrame(index) {
            currentRenderedIndex = index;
            const frameImg = getBestAvailableFrame(index);
            if (frameImg) {
                requestAnimationFrame(function () {
                    drawCover(frameImg);
                });
            }
        }

        // 1. Load First Frame IMMEDIATELY (Requirement 9: Non-blocking & instant initial view)
        const firstFrame = new Image();
        firstFrame.src = getFrameUrl(1);
        firstFrame.onload = function () {
            firstFrame.isLoaded = true;
            frames[1] = firstFrame;
            loadedCount++;
            resizeCanvas();
            renderFrame(1);
            startBackgroundPreloading();
        };
        firstFrame.onerror = function () {
            console.warn("Failed to load initial frame 1. Retrying...");
            startBackgroundPreloading();
        };

        // 2. Progressive non-blocking background frame loader
        function startBackgroundPreloading() {
            // Queue frame indices 2 through 95
            const queue = [];
            for (let i = 2; i <= TOTAL_FRAMES; i++) {
                queue.push(i);
            }

            const BATCH_SIZE = 4;
            let activeLoads = 0;

            function pumpQueue() {
                while (queue.length > 0 && activeLoads < BATCH_SIZE) {
                    const idx = queue.shift();
                    activeLoads++;

                    const img = new Image();
                    img.src = getFrameUrl(idx);
                    img.onload = function () {
                        img.isLoaded = true;
                        frames[idx] = img;
                        loadedCount++;
                        activeLoads--;

                        if (loaderHud) {
                            loaderHud.textContent = `Scene 1 Assets: ${loadedCount} / ${TOTAL_FRAMES}`;
                            if (loadedCount >= TOTAL_FRAMES) {
                                loaderHud.classList.add("loaded");
                                setTimeout(() => { loaderHud.style.display = "none"; }, 500);
                            }
                        }

                        // If user is currently positioned at this frame, re-render with higher fidelity
                        if (currentRenderedIndex === idx) {
                            renderFrame(idx);
                        }

                        pumpQueue();
                    };
                    img.onerror = function () {
                        activeLoads--;
                        pumpQueue();
                    };
                }
            }

            pumpQueue();
        }

        window.addEventListener("resize", resizeCanvas, { passive: true });
        resizeCanvas();

        // 3. GSAP & ScrollTrigger Setup (Requirements 6, 7 & 8)
        if (typeof gsap === "undefined" || typeof ScrollTrigger === "undefined") {
            console.warn("GSAP or ScrollTrigger CDN not loaded. Fallback to static frame 1.");
            return;
        }

        gsap.registerPlugin(ScrollTrigger);

        // Pre-create frame timeline with scrub
        const timeline = gsap.timeline({
            scrollTrigger: {
                trigger: container,
                start: "top top",
                end: "+=2600",
                pin: true,
                scrub: 0.5, // Smooth forwards & backwards scrub
                anticipatePin: 1,
                onUpdate: function (self) {
                    const progress = self.progress;
                    const targetFrame = Math.min(
                        TOTAL_FRAMES,
                        Math.max(1, Math.round(progress * (TOTAL_FRAMES - 1) + 1))
                    );

                    if (targetFrame !== currentRenderedIndex) {
                        renderFrame(targetFrame);
                    }

                    if (progressBar) {
                        progressBar.style.width = (progress * 100).toFixed(1) + "%";
                    }
                }
            }
        });

        // 4. Independent Headline Animation (Requirement 8)
        if (overlay) {
            timeline.to(overlay, {
                opacity: 0,
                y: -50,
                duration: 0.35,
                ease: "power2.out"
            }, 0.1);
        }
    });
})();
