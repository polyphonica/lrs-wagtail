// Mobile menu toggle, and YouTube videos and maps that load only when played or clicked (faster pages, no tracking until then).
document.documentElement.classList.add("js");
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.getElementById("site-nav");
  if (toggle && nav) {
    toggle.hidden = false;
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open);
    });
  }
  // Signed-in "My account" dropdown (wide screens; on phones its links sit in the menu).
  const account = document.querySelector(".account-toggle");
  const accountMenu = document.getElementById("account-menu");
  if (account && accountMenu) {
    account.hidden = false;
    const setOpen = (open) => {
      accountMenu.classList.toggle("open", open);
      account.setAttribute("aria-expanded", open);
    };
    account.addEventListener("click", () => setOpen(!accountMenu.classList.contains("open")));
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".account")) setOpen(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && accountMenu.classList.contains("open")) { setOpen(false); account.focus(); }
    });
  }
  // Google map that loads only when clicked (Google sees nothing until then).
  document.querySelectorAll("a.map[data-map]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const frame = document.createElement("iframe");
      frame.src = link.dataset.map;
      frame.title = "Map of the rehearsal venue";
      frame.referrerPolicy = "no-referrer-when-downgrade";
      const box = document.createElement("div");
      box.className = "map";
      box.append(frame);
      link.replaceWith(box);
    }, { once: true });
  });
  document.querySelectorAll("a.yt[data-yt]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const frame = document.createElement("iframe");
      frame.src = `https://www.youtube-nocookie.com/embed/${link.dataset.yt}?autoplay=1&rel=0`;
      frame.title = link.textContent.trim() || "Video";
      frame.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
      frame.allowFullscreen = true;
      link.replaceChildren(frame);
    }, { once: true });
  });
});
