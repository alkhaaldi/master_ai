/* datastate-notice.js — Phase 2, Section G-6
   تُضاف إلى الصفحات التي تعرض أرقام سوق ولا تعلن حالة بياناتها.
   لا تدّعي أن الصفحة مؤرشفة ولا أن أرقامها خاطئة — تقول الحقيقة
   الوحيدة المؤكدة عنها: أنها لا تصرّح بعمر ما تعرضه.
   الصفحات التي تعلن حالتها لا تحتاجها ولا تحملها. */
(function () {
  var LIVE = 'radar · positions · swing · decisions';
  function inject() {
    if (document.getElementById('ds-notice')) return;
    var el = document.createElement('div');
    el.id = 'ds-notice';
    el.setAttribute('dir', 'rtl');
    el.style.cssText = [
      'background:rgba(232,168,56,.10)',
      'border-bottom:1px solid rgba(232,168,56,.38)',
      'color:#E8A838',
      'font-family:Tajawal,system-ui,sans-serif',
      'font-size:.74rem',
      'line-height:1.6',
      'padding:.55rem .9rem',
      'display:flex',
      'gap:.6rem',
      'align-items:flex-start',
      'flex-wrap:wrap'
    ].join(';');
    el.innerHTML =
      '<span style="font-size:.95rem;line-height:1.2">\u25B2</span>' +
      '<div style="flex:1;min-width:200px">' +
        '<div style="font-weight:700">\u0647\u0630\u0647 \u0627\u0644\u0635\u0641\u062D\u0629 \u0644\u0627 \u062A\u0639\u0644\u0646 \u062D\u0627\u0644\u0629 \u0628\u064A\u0627\u0646\u0627\u062A\u0647\u0627</div>' +
        '<div style="opacity:.85;font-weight:400">' +
          '\u0642\u062F \u062A\u0643\u0648\u0646 \u0627\u0644\u0623\u0631\u0642\u0627\u0645 \u0645\u0646 \u062C\u0644\u0633\u0629 \u0633\u0627\u0628\u0642\u0629 \u060C ' +
          '\u0648\u0644\u064A\u0633 \u0641\u064A\u0647\u0627 \u0645\u0627 \u064A\u0642\u0648\u0644 \u0645\u062A\u0649 \u0642\u064A\u0633\u062A. ' +
          '\u0644\u0644\u062D\u0627\u0644\u0629 \u0627\u0644\u0645\u0639\u0644\u0646\u0629: <span style="direction:ltr;display:inline-block;font-family:ui-monospace,monospace;font-size:.68rem">' + LIVE + '</span>' +
        '</div>' +
      '</div>';
    var b = document.body;
    if (b) b.insertBefore(el, b.firstChild);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
