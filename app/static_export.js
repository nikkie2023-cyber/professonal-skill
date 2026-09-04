(function () {
  var style = document.createElement('style'); style.textContent = '.visual-guidance{background:#f4f2ff;border-left:3px solid #5b43e6;padding:7px 9px;border-radius:5px;font-size:12px;line-height:1.55}.visual-guidance b{color:#4f3bc4}#exportPack{margin:18px 0 0 12px}.cover-analysis{margin:24px 0;padding:18px 20px;border:1px solid #e2e8f0;border-radius:14px;background:#fbfcff}.cover-title{display:flex;gap:12px;align-items:baseline;margin-bottom:14px}.cover-title b{font-size:20px;color:#111827}.cover-title span{font-size:13px;color:#64748b}.cover-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.cover-grid>div{padding:12px;background:#fff;border:1px solid #edf0f5;border-radius:10px;min-height:62px}.cover-grid small{display:block;color:#64748b;margin-bottom:5px}.cover-grid strong{font-weight:600;color:#1f2937}.cover-advice{margin-top:12px;padding:12px 14px;background:#fff;border-left:3px solid #5b43e6;line-height:1.8;color:#374151}@media(max-width:800px){.cover-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}'; document.head.appendChild(style);
  function addButton() {
    var container = document.getElementById('generatedScript');
    if (!container || document.getElementById('exportPack')) return;
    var button = document.createElement('button');
    button.id = 'exportPack';
    button.className = 'export';
    button.type = 'button';
    button.textContent = '⇩ 导出完整拍摄 Excel';
    button.onclick = exportPack;
    container.insertBefore(button, container.firstChild);
  }
  function addVisualGuidance(data) {
    var shots = Array.isArray(data.shots) ? data.shots : [];
    document.querySelectorAll('.story-card').forEach(function (card, index) {
      var shot = shots[index];
      if (!shot || card.querySelector('.visual-guidance')) return;
      var box = document.createElement('div');
      box.className = 'visual-guidance';
      box.innerHTML = '<b>标准画面指导</b><br>机位：' + (shot.camera_angle || '手机固定机位') + '<br>构图：' + (shot.composition || '主体与商品同框') + '<br>画面证据：' + (shot.visual_evidence || '使用真实可验证画面');
      card.querySelector('.story-copy').prepend(box);
    });
  }
  function exportPack() {
    if (!window.generatedScriptData || !window.currentReport) return;
    fetch('/api/export-script', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ report: window.currentReport, script: window.generatedScriptData }) })
      .then(function (res) { if (!res.ok) throw new Error('Excel导出失败'); return res.blob(); })
      .then(function (blob) { var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'content_replication_shooting_pack.xlsx'; a.click(); URL.revokeObjectURL(a.href); })
      .catch(function (err) { var box = document.getElementById('productError'); if (box) { box.textContent = err.message; box.style.display = 'block'; } });
  }
  function installVideoUrlPreflight() {
    var form = document.getElementById('form');
    if (!form || form.dataset.preflightInstalled) return;
    form.dataset.preflightInstalled = '1';
    function showEstimate() {
      var progress = document.getElementById('progress');
      if (!progress || document.getElementById('progressEstimate')) return;
      var estimate = document.createElement('div');
      estimate.id = 'progressEstimate';
      estimate.textContent = '预计耗时：约 1–3 分钟，取决于视频时长、截图数量和模型响应速度';
      estimate.style.cssText = 'margin:4px 0 8px;color:#64748b;font-size:13px';
      var title = document.getElementById('progress-title');
      if (title) title.insertAdjacentElement('afterend', estimate);
    }
    var bypass = false;
    form.addEventListener('submit', function (event) {
      if (bypass) { bypass = false; return; }
      var file = document.getElementById('file');
      var url = document.getElementById('url');
      if (!url || !url.value.trim() || (file && file.files && file.files.length)) { showEstimate(); return; }
      event.preventDefault();
      event.stopImmediatePropagation();
      var progress = document.getElementById('progress');
      var error = document.getElementById('error');
      if (progress) progress.classList.remove('show');
      if (error) {
        error.className = 'url-warning';
        error.innerHTML = '<b>⚠ 正在检查视频链接</b><br>确认链接是否返回视频文件，请稍候…';
        error.style.display = 'block';
      }
      fetch('/api/check-video-url', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url: url.value.trim() }) })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          if (!data.readable) {
            if (progress) progress.classList.remove('show');
            if (error) {
              error.className = 'url-warning';
              error.innerHTML = '<b>⚠ 无法读取视频内容</b><br>' + (data.reason || '当前链接返回的是网页或受限页面') + '<br><span>请上传视频文件后继续分析。</span><button type="button" class="choose-video">选择视频文件</button>';
              error.style.display = 'block';
              var choose = error.querySelector('.choose-video');
              if (choose) choose.onclick = function () { if (file) file.click(); };
            }
            return;
          }
          if (error) error.style.display = 'none';
          showEstimate();
          bypass = true;
          form.requestSubmit();
        })
        .catch(function (err) {
          if (progress) progress.classList.remove('show');
          if (error) {
            error.className = 'url-warning';
            error.innerHTML = '<b>⚠ 无法确认视频链接</b><br>' + String(err.message || '服务器暂时无法检查链接') + '<br><span>请上传视频文件后继续分析。</span>';
            error.style.display = 'block';
          }
        });
    }, true);
  }
  var preflightStyle = document.createElement('style');
  preflightStyle.textContent = '.url-warning{display:none;margin-top:15px;padding:14px 16px;border:1px solid #f2bf67;border-radius:10px;background:#fff8e8;color:#8a5a08;line-height:1.8}.url-warning b{font-size:15px;color:#b45309}.url-warning span{color:#5f6775}.choose-video{display:block;margin-top:10px;padding:8px 12px;border:0;border-radius:7px;background:#5b43e6;color:#fff;cursor:pointer}';
  document.head.appendChild(preflightStyle);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installVideoUrlPreflight); else installVideoUrlPreflight();
  function installAsyncAnalysis() {
    var form = document.getElementById('form');
    if (!form || form.dataset.asyncAnalysisInstalled) return;
    form.dataset.asyncAnalysisInstalled = '1';
    var labels = {
      queued: '\u7b49\u5f85\u5f00\u59cb',
      metadata: '\u6b63\u5728\u89e3\u6790\u89c6\u9891\u4fe1\u606f',
      extracting_frames: '\u6b63\u5728\u63d0\u53d6\u5173\u952e\u622a\u56fe',
      vision_analysis: '\u6b63\u5728\u8fdb\u884c\u89c6\u9891\u7406\u89e3',
      structuring_report: '\u6b63\u5728\u6574\u7406\u9010\u955c\u5934\u62a5\u544a',
      text_analysis: '\u6b63\u5728\u5b8c\u5584\u590d\u523b\u5efa\u8bae',
      finalizing: '\u6b63\u5728\u4fdd\u5b58\u5206\u6790\u7ed3\u679c',
      completed: '\u5206\u6790\u5b8c\u6210',
      failed: '\u5206\u6790\u5931\u8d25'
    };
    function formatEstimate(seconds) {
      seconds = Number(seconds || 0);
      if (seconds >= 60) return '\u9884\u8ba1\u8017\u65f6\uff1a\u7ea6 ' + Math.ceil(seconds / 60) + '\u5206\u949f\uff08\u53ea\u662f\u53c2\u8003\uff0c\u4e0d\u662f\u5012\u8ba1\u65f6\uff09';
      return '\u9884\u8ba1\u8017\u65f6\uff1a\u7ea6 ' + Math.max(1, Math.ceil(seconds)) + '\u79d2\uff08\u53ea\u662f\u53c2\u8003\uff09';
    }
    function setProgress(job) {
      var box = document.getElementById('progress');
      if (!box) return;
      box.classList.add('show');
      var title = document.getElementById('progress-title');
      if (title) title.textContent = labels[job.stage] || labels[job.status] || '\u6b63\u5728\u5904\u7406';
      var bar = box.querySelector('.progress-line i');
      if (bar) { bar.style.animation = 'none'; bar.style.width = Math.max(3, Math.min(100, Number(job.progress || 0))) + '%'; }
      var estimate = document.getElementById('progressEstimate');
      if (!estimate) {
        estimate = document.createElement('div'); estimate.id = 'progressEstimate';
        estimate.style.cssText = 'margin:4px 0 8px;color:#64748b;font-size:13px';
        if (title) title.insertAdjacentElement('afterend', estimate);
      }
      estimate.textContent = formatEstimate(job.estimated_seconds);
      var items = Object.keys(labels).filter(function (key) { return !['queued','completed','failed'].includes(key); });
      var list = document.getElementById('progress-list');
      if (list) list.innerHTML = items.map(function (key) { return '<li class="' + (job.stage === key || Number(job.progress || 0) > (items.indexOf(key) + 1) * 14 ? 'done' : '') + '">' + labels[key] + '</li>'; }).join('');
    }
    function showError(message) {
      var error = document.getElementById('error');
      if (!error) return;
      error.className = 'error'; error.textContent = message || '\u670d\u52a1\u5668\u5904\u7406\u5931\u8d25'; error.style.display = 'block';
    }
    function loadReport(reportId) {
      return fetch('/api/report/' + encodeURIComponent(reportId)).then(function (res) {
        if (!res.ok) throw new Error('\u627e\u4e0d\u5230\u5206\u6790\u62a5\u544a');
        return res.json();
      }).then(function (data) {
        if (window.__setReport) window.__setReport(data);
        window.currentReport = data;
        if (window.renderReport) window.renderReport(data);
        var result = document.getElementById('result');
        if (result) { result.style.display = 'block'; result.scrollIntoView({ behavior: 'smooth' }); }
      });
    }
    function poll(jobId) {
      fetch('/api/analyze-status/' + encodeURIComponent(jobId)).then(function (res) {
        if (!res.ok) throw new Error('\u5206\u6790\u4efb\u52a1\u4e0d\u5b58\u5728');
        return res.json();
      }).then(function (job) {
        setProgress(job);
        if (job.status === 'completed' && job.report_id) {
          setStep(3); return loadReport(job.report_id);
        }
        if (job.status === 'failed') throw new Error(job.error || '\u89c6\u9891\u5206\u6790\u5931\u8d25');
        if (job.status === 'processing') setStep(job.progress >= 75 ? 2 : 1);
        window.setTimeout(function () { poll(jobId); }, 1200);
      }).catch(function (err) { var progress = document.getElementById('progress'); if (progress) progress.classList.remove('show'); showError(err.message); setStep(0); });
    }
    form.addEventListener('submit', function (event) {
      event.preventDefault(); event.stopImmediatePropagation();
      var error = document.getElementById('error'); if (error) error.style.display = 'none';
      setStep(1); setProgress({ status: 'queued', stage: 'queued', progress: 0, estimated_seconds: 120 });
      fetch('/api/analyze-async', { method: 'POST', body: new FormData(form) }).then(function (res) {
        return res.json().then(function (data) { if (!res.ok) throw new Error(data.error || '\u670d\u52a1\u5668\u63a5\u6536\u89c6\u9891\u5931\u8d25'); return data; });
      }).then(function (job) { setProgress(job); poll(job.job_id); }).catch(function (err) { var progress = document.getElementById('progress'); if (progress) progress.classList.remove('show'); showError(err.message); setStep(0); });
    }, true);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', installAsyncAnalysis); else installAsyncAnalysis();
  var oldRender = window.renderGeneratedScript;
  if (oldRender) {
    window.renderGeneratedScript = function (data) { window.generatedScriptData = data; oldRender(data); addButton(); addVisualGuidance(data); };
  }
  function addCoverAnalysis(data) {
    var cover = data && data.cover_analysis;
    if (!cover || document.getElementById('coverAnalysis')) return;
    var table = document.querySelector('.shot-table');
    if (!table) return;
    var section = document.createElement('section');
    section.id = 'coverAnalysis';
    section.className = 'cover-analysis';
    section.innerHTML = '<div class="cover-title"><b>封面分析</b><span>判断用户为什么点击，以及哪些封面元素可以复刻</span></div>' +
      '<div class="cover-grid">' +
      item('封面主体', cover.main_subject) + item('封面文字', cover.cover_text) +
      item('目标人群', cover.target_audience) + item('点击理由', cover.click_reason) +
      item('视觉层级', cover.visual_hierarchy) + item('文字可读性', cover.text_readability) +
      item('封面承诺与视频一致性', cover.promise_match) + item('复刻判断', cover.replication_level) +
      '</div><div class="cover-advice"><b>复刻依据：</b>' + escText(cover.replication_reason) + '<br><b>用户改造建议：</b>' + escText(cover.adaptation_advice) + '<br><b>风险：</b>' + escText(cover.risks) + '</div>';
    var wrap = table.closest('.panel') || table.parentElement;
    wrap.insertBefore(section, wrap.querySelector('.table-wrap') || table);
    function item(label, value) { return '<div><small>' + label + '</small><strong>' + escText(value) + '</strong></div>'; }
    function escText(value) { return String(value || '未识别').replace(/[&<>"']/g, function (ch) { return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[ch]; }); }
  }
  var oldRenderReport = window.renderReport;
  if (oldRenderReport) {
    window.renderReport = function (data) { window.currentReport = data; oldRenderReport(data); addCoverAnalysis(data); };
  }
  function loadImportedReference() {
    var referenceId = new URLSearchParams(location.search).get('reference_id');
    if (!referenceId) return;
    fetch('/api/reference/' + encodeURIComponent(referenceId)).then(function (res) {
      if (!res.ok) throw new Error('找不到导入的参考内容');
      return res.json();
    }).then(function (reference) {
      var input = document.getElementById('url');
      if (input) input.value = reference.url || '';
      var error = document.getElementById('error');
      if (error) {
        error.className = 'notice';
        error.textContent = '已载入插件保存的参考链接：' + (reference.title || reference.url || '') + '。请确认分析目标后点击“开始拆解”。';
        error.style.display = 'block';
      }
    }).catch(function (err) {
      var error = document.getElementById('error');
      if (error) { error.textContent = err.message; error.style.display = 'block'; }
    });
  }
  function loadImportedReport() {
    var reportId = new URLSearchParams(location.search).get('report_id');
    if (!reportId || !window.renderReport) return;
    fetch('/api/report/' + encodeURIComponent(reportId)).then(function (res) {
      if (!res.ok) throw new Error('找不到自动分析结果');
      return res.json();
    }).then(function (data) {
      window.currentReport = data;
      window.renderReport(data);
      var result = document.getElementById('result');
      if (result) { result.style.display = 'block'; result.scrollIntoView({ behavior: 'smooth' }); }
    }).catch(function (err) {
      var error = document.getElementById('error');
      if (error) { error.textContent = err.message; error.style.display = 'block'; }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadImportedReference); else loadImportedReference();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', loadImportedReport); else loadImportedReport();
})();
