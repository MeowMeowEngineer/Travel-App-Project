/* GA4 custom events (gtag, or dataLayer events for Google Tag Manager) for outbound actions (map, route, official info, stays, food ...).
   Links carry data-track="<event_name>" plus optional data-place / data-provider (and, in the site assistant's
   answers, data-chat-where: 'panel' | 'dock' — the floating panel or the homes' centre question card).
   GA4 enhanced measurement also records outbound clicks; these events add meaning.
   Register place_id / link_provider / page_kind / chat_where as custom dimensions in GA4 to report on them. */
(function () {
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a[data-track]') : null;
    if (!a) return;
    var name = a.getAttribute('data-track');
    var params = {
      link_url: a.href,
      place_id: a.getAttribute('data-place') || '',
      link_provider: a.getAttribute('data-provider') || '',
      page_kind: document.body.getAttribute('data-page-kind') || ''
    };
    if (a.hasAttribute('data-chat-where')) params.chat_where = a.getAttribute('data-chat-where');
    if (typeof window.gtag === 'function') { window.gtag('event', name, params); return; }
    // Google Tag Manager: the same event as a dataLayer push (a GTM trigger on event = name sends it to GA4)
    if (window.dataLayer && window.dataLayer.push) {
      var ev = { event: name };
      for (var k in params) ev[k] = params[k];
      window.dataLayer.push(ev);
    }
  }, true);
})();
