async function applyWdgNavVisibility() {
  try {
    const res = await fetch("/dashboard/api/settings", { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    const show = data.wdgwars?.configured === true;
    document.querySelectorAll("[data-wdg-nav]").forEach((el) => {
      el.hidden = !show;
    });
    return data.wdgwars;
  } catch {
    document.querySelectorAll("[data-wdg-nav]").forEach((el) => {
      el.hidden = true;
    });
    return null;
  }
}
