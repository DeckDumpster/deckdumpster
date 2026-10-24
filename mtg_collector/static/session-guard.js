// An expired or missing sign-in: any in-page request the middleware refuses with
// 401 + X-Login-Required sends the browser to the login page, and login returns
// here. Loaded into every HTML document by static_assets.AssetHasher.rewrite.
(function () {
  const nativeFetch = window.fetch;
  function toLogin() {
    const here = location.pathname + location.search + location.hash;
    location.assign('/auth/login?return_to=' + encodeURIComponent(here));
    return new Promise(function () {});  // never settles: no error UI flashes before the redirect
  }
  window.fetch = function () {
    return nativeFetch.apply(this, arguments).then(function (resp) {
      return resp.status === 401 && resp.headers.get('X-Login-Required') ? toLogin() : resp;
    });
  };
  const nativeSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener('readystatechange', function () {
      if (this.readyState === 4 && this.status === 401 && this.getResponseHeader('X-Login-Required')) toLogin();
    });
    return nativeSend.apply(this, arguments);
  };
})();
