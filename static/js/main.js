/**
 * International Currency Exchange Rate Tracker - Front-end Engine
 * Split-flap departure board simulation, smooth entrance, and mobile navigation.
 */

document.addEventListener("DOMContentLoaded", function () {
    // 1. Accessible Mobile Navigation
    const menuToggle = document.querySelector(".menu-toggle");
    const navMenu = document.querySelector(".nav-menu");

    if (menuToggle && navMenu) {
        menuToggle.addEventListener("click", function () {
            const isExpanded = menuToggle.getAttribute("aria-expanded") === "true";
            menuToggle.setAttribute("aria-expanded", !isExpanded);
            navMenu.classList.toggle("open");
        });

        // Close menu when clicking outside
        document.addEventListener("click", function (event) {
            if (!menuToggle.contains(event.target) && !navMenu.contains(event.target)) {
                navMenu.classList.remove("open");
                menuToggle.setAttribute("aria-expanded", "false");
            }
        });

        // Close on Escape key
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape" && navMenu.classList.contains("open")) {
                navMenu.classList.remove("open");
                menuToggle.setAttribute("aria-expanded", "false");
                menuToggle.focus();
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

