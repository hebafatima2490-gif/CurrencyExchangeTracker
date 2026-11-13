/**
 * International Currency Exchange Rate Tracker - Front-end Engine
 * Global Wealth Institutional Theme & Unified Top Navigation
 * Split-flap departure board simulation, smooth entrance, and mobile navigation.
 */

document.addEventListener("DOMContentLoaded", function () {
    // 1. Unified Mobile Top Navigation Menu Toggle
    const mobileToggle = document.getElementById("mobileNavToggle") || document.querySelector(".topbar-menu-toggle");
    const topbarNav = document.getElementById("topbarNav");

    if (mobileToggle && topbarNav) {
        mobileToggle.addEventListener("click", function (e) {
            e.stopPropagation();
            const isOpen = topbarNav.classList.toggle("open");
            mobileToggle.setAttribute("aria-expanded", String(isOpen));
        });

        // Close mobile menu when clicking outside
        document.addEventListener("click", function (e) {
            if (!mobileToggle.contains(e.target) && !topbarNav.contains(e.target)) {
                topbarNav.classList.remove("open");
                mobileToggle.setAttribute("aria-expanded", "false");
            }
        });

        // Close mobile menu on Escape key
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && topbarNav.classList.contains("open")) {
                topbarNav.classList.remove("open");
                mobileToggle.setAttribute("aria-expanded", "false");
                mobileToggle.focus();
            }
        });
    }

    // 2. Departure Board Intro Animation & Session Persistence (Dashboard only)
    const boardHero = document.getElementById("bureauBoardHero");
    const skipBtn = document.getElementById("skipBoardBtn");
    const scrollCue = document.getElementById("boardScrollCue");
    const dashboardAnchor = document.getElementById("dashboard-rates");

    if (boardHero) {
        const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        const alreadySeen = sessionStorage.getItem("bureau_board_seen") === "true";

        if (prefersReducedMotion || alreadySeen) {
            // Instant display without animation
            boardHero.classList.remove("flap-animated");
        } else {
            // Play split-flap departure sequence
            boardHero.classList.add("flap-animated");
            sessionStorage.setItem("bureau_board_seen", "true");
            setTimeout(function () {
                boardHero.classList.remove("flap-animated");
            }, 1200);
        }

        // Skip button handler
        if (skipBtn && dashboardAnchor) {
            skipBtn.addEventListener("click", function (e) {
                e.preventDefault();
                sessionStorage.setItem("bureau_board_seen", "true");
                dashboardAnchor.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        }

        // Scroll cue handler
        if (scrollCue && dashboardAnchor) {
            scrollCue.addEventListener("click", function (e) {
                e.preventDefault();
                dashboardAnchor.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        }
    }
});
