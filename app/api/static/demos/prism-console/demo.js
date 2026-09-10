(() => {
  const views = {
    agent: document.querySelector("#view-agent"),
    overview: document.querySelector("#view-overview"),
  };
  const context = document.querySelector("#page-context");

  function showView(name) {
    if (!views[name]) return;
    Object.entries(views).forEach(([key, view]) => {
      const active = key === name;
      view.hidden = !active;
      view.classList.toggle("active", active);
    });
    document.querySelectorAll("[data-view]").forEach((item) => {
      const active = item.dataset.view === name;
      item.classList.toggle("active", active);
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
    context.textContent = name === "overview" ? "我的组合" : "Agent 对话";
    history.replaceState(null, "", `#${name}`);
    document.body.classList.remove("nav-open");
  }

  document.querySelectorAll("[data-view]").forEach((item) => {
    item.addEventListener("click", () => showView(item.dataset.view));
  });

  document.querySelector(".mobile-nav").addEventListener("click", () => {
    document.body.classList.toggle("nav-open");
  });

  document.querySelectorAll(".segmented button").forEach((button) => {
    button.addEventListener("click", () => {
      button.parentElement.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    });
  });

  document.querySelectorAll(".suggestions button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelector("#question").value = button.textContent.trim();
      document.querySelector("#question").focus();
    });
  });

  document.querySelector("#demo-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.querySelector("#question");
    const value = input.value.trim();
    if (!value) return input.focus();
    const messages = document.querySelector("#messages");
    messages.replaceChildren();
    const message = document.createElement("div");
    message.className = "demo-message";
    message.textContent = value;
    messages.append(message);
    input.value = "";
  });

  showView(location.hash === "#overview" ? "overview" : "agent");
})();
