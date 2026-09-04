const $ = (id) => document.getElementById(id);

async function getPageInfo(tabId) {
  const result = await chrome.scripting.executeScript({
    target: { tabId },
    func: async () => {
      const meta = (selector) => document.querySelector(selector)?.content || "";
      const candidates = [...document.querySelectorAll("video, video source")]
        .map((node) => node.currentSrc || node.src || "")
        .filter((url) => /^https?:\/\//i.test(url) || /^blob:/i.test(url));
      const resources = performance.getEntriesByType("resource")
        .map((entry) => entry.name || "")
        .filter((url) => /\.(mp4|webm|mov)(\?|$)/i.test(url));
      const mediaUrls = [...new Set([...candidates, ...resources])].slice(0, 5);
      let captured = null;
      for (const mediaUrl of mediaUrls) {
        try {
          const response = await fetch(mediaUrl, { credentials: "include" });
          const type = response.headers.get("content-type") || "";
          const blob = await response.blob();
          if (!blob.size || blob.size > 50 * 1024 * 1024 || (!type.startsWith("video/") && !blob.type.startsWith("video/"))) continue;
          const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          });
          captured = { data_url: dataUrl, mime_type: blob.type || type || "video/mp4", filename: "browser-captured-video.mp4" };
          break;
        } catch (_) {
          // Protected or segmented playback is expected to fail here.
        }
      }
      return {
        url: location.href,
        title: document.title || "",
        cover_url: meta('meta[property="og:image"]') || meta('meta[name="twitter:image"]') || "",
        author: meta('meta[name="author"]') || "",
        media_urls: mediaUrls,
        captured
      };
    }
  });
  return result?.[0]?.result || { url: "", title: "", cover_url: "", author: "" };
}

function dataUrlToBlob(dataUrl) {
  const [header, encoded] = dataUrl.split(",", 2);
  const mime = (header.match(/data:([^;]+)/i) || [])[1] || "video/mp4";
  const binary = atob(encoded || "");
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

async function init() {
  const saved = await chrome.storage.sync.get({ endpoint: "http://127.0.0.1:8000" });
  $("endpoint").value = saved.endpoint;
}

$("send").addEventListener("click", async () => {
  const button = $("send");
  const status = $("status");
  button.disabled = true;
  status.className = "";
  status.textContent = "Reading the current page and trying to capture video...";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const info = await getPageInfo(tab.id);
    if (!/^https?:\/\//i.test(info.url)) throw new Error("The current page is not a normal web page.");
    const endpoint = $("endpoint").value.trim().replace(/\/$/, "");
    await chrome.storage.sync.set({ endpoint });
    let response;
    if (info.captured?.data_url) {
      status.textContent = "Video captured. Uploading and analyzing...";
      const form = new FormData();
      form.append("video", dataUrlToBlob(info.captured.data_url), info.captured.filename || "browser-captured-video.mp4");
      form.append("goal", "commerce");
      form.append("source_url", info.url);
      form.append("profile_notes", $("note").value);
      response = await fetch(`${endpoint}/api/import-media`, { method: "POST", body: form });
    } else {
      status.textContent = "The player is protected. Saving the reference link instead...";
      response = await fetch(`${endpoint}/api/import-reference`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...info, platform: $("platform").value, note: $("note").value, source: "browser_extension", capture_status: "unavailable" })
      });
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Save failed");
    status.className = "ok";
    status.textContent = info.captured ? "Video submitted. Opening the result..." : "Reference saved. Opening the workbench...";
    const nextUrl = data.report_id ? `${endpoint}/?report_id=${encodeURIComponent(data.report_id)}` : `${endpoint}${data.analysis_url}`;
    chrome.tabs.create({ url: nextUrl });
  } catch (error) {
    status.className = "error";
    status.textContent = `Send failed: ${error.message}\nCheck that the workbench is running and the address is correct.`;
  } finally {
    button.disabled = false;
  }
});

init();
