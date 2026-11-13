/**
 * International Currency Exchange Rate Tracker - Authenticated User Navigation
 * Accessible dropdown and mobile navigation handlers for logged-in users.
 */
(function () {
    "use strict";

    function initAcctNav() {
        const userBtn = document.getElementById("acctUserBtn");
        const dropdownMenu = document.getElementById("acctDropdownMenu");
        const menuToggle = document.querySelector(".acct-menu-toggle");
        const navMenu = document.getElementById("acctPrimaryNav");

        // Safe return if account header is not present on the page
        if (!userBtn && !menuToggle) {
            return;
        }

        // --- 1. Username Dropdown Handler ---
        if (userBtn && dropdownMenu) {
            function openDropdown() {
                userBtn.setAttribute("aria-expanded", "true");
                dropdownMenu.classList.add("acct-open");
            }

            function closeDropdown(focusButton) {
                if (userBtn.getAttribute("aria-expanded") === "true") {
                    userBtn.setAttribute("aria-expanded", "false");
                    dropdownMenu.classList.remove("acct-open");
                    if (focusButton) {
                        userBtn.focus();
                    }
                }
            }

            function toggleDropdown() {
                const isOpen = userBtn.getAttribute("aria-expanded") === "true";
                if (isOpen) {
                    closeDropdown(false);
                } else {
                    openDropdown();
                }
            }

            userBtn.addEventListener("click", function (e) {
                e.stopPropagation();
                toggleDropdown();
            });

            // Close dropdown when clicking outside
            document.addEventListener("click", function (e) {
                if (!userBtn.contains(e.target) && !dropdownMenu.contains(e.target)) {
                    closeDropdown(false);
                }
            });

            // Keyboard accessibility: Escape key closes dropdown
            document.addEventListener("keydown", function (e) {
                if (e.key === "Escape" && userBtn.getAttribute("aria-expanded") === "true") {
                    closeDropdown(true);
                }
            });

            // Keyboard navigation inside dropdown menu
            dropdownMenu.addEventListener("keydown", function (e) {
                const items = Array.from(dropdownMenu.querySelectorAll(".acct-dropdown-item"));
                const currentIndex = items.indexOf(document.activeElement);

                if (e.key === "ArrowDown") {
                    e.preventDefault();
                    const nextIndex = (currentIndex + 1) % items.length;
                    items[nextIndex].focus();
                } else if (e.key === "ArrowUp") {
                    e.preventDefault();
                    const prevIndex = (currentIndex - 1 + items.length) % items.length;
                    items[prevIndex].focus();
                } else if (e.key === "Tab" && !e.shiftKey && currentIndex === items.length - 1) {
                    closeDropdown(false);
                }
            });
        }

        // --- 2. Mobile Menu Toggle Handler ---
        if (menuToggle && navMenu) {
            menuToggle.addEventListener("click", function (e) {
                e.stopPropagation();
                const isExpanded = menuToggle.getAttribute("aria-expanded") === "true";
                menuToggle.setAttribute("aria-expanded", String(!isExpanded));
                navMenu.classList.toggle("acct-nav-open");
            });

            // Close mobile menu when clicking outside
            document.addEventListener("click", function (e) {
                if (!menuToggle.contains(e.target) && !navMenu.contains(e.target)) {
                    navMenu.classList.remove("acct-nav-open");
                    menuToggle.setAttribute("aria-expanded", "false");
                }
            });

            // Close mobile menu on Escape key
            document.addEventListener("keydown", function (e) {
                if (e.key === "Escape" && navMenu.classList.contains("acct-nav-open")) {
                    navMenu.classList.remove("acct-nav-open");
                    menuToggle.setAttribute("aria-expanded", "false");
                    menuToggle.focus();
                }
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initAcctNav);
    } else {
        initAcctNav();
    }
})();

