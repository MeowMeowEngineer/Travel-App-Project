/* a stand-in for the Kakao Maps SDK in browser tests: just what map.js calls. One flat plane (1e5 units a degree);
   an overlay's element is in the box while it is on the map, so a test reads the shown markers from the DOM. */
(function () {
  function Coords(x, y) { this.x = x; this.y = y; }
  Coords.prototype.getX = function () { return this.x; };
  Coords.prototype.getY = function () { return this.y; };
  Coords.prototype.toLatLng = function () { return new LatLng(this.y / 1e5, this.x / 1e5); };
  function LatLng(a, b) { this.a = a; this.b = b; }
  LatLng.prototype.getLat = function () { return this.a; };
  LatLng.prototype.getLng = function () { return this.b; };
  LatLng.prototype.toCoords = function () { return new Coords(this.b * 1e5, this.a * 1e5); };
  function Map(box, o) { this.box = box; this.c = o.center; this.lv = o.level; this.layer = document.createElement("div"); box.appendChild(this.layer); }
  Map.prototype.getCenter = function () { return this.c; };
  Map.prototype.setCenter = function (c) { this.c = c; };
  Map.prototype.getLevel = function () { return this.lv; };
  Map.prototype.setLevel = function (lv) { this.lv = lv; };
  Map.prototype.panTo = function (c) { this.c = c; };
  Map.prototype.panBy = function () {};
  Map.prototype.relayout = function () {};
  Map.prototype.setCopyrightPosition = function () {};
  Map.prototype.getBounds = function () {
    var u = 2.5 * Math.pow(2, this.lv - 3) / 1e5, w = this.box.clientWidth * u / 2, h = this.box.clientHeight * u / 2, c = this.c;
    return { getSouthWest: function () { return new LatLng(c.a - h, c.b - w); }, getNorthEast: function () { return new LatLng(c.a + h, c.b + w); } };
  };
  function CustomOverlay(o) { this.o = o; this.m = null; }
  CustomOverlay.prototype.setMap = function (m) {
    if (m) m.layer.appendChild(this.o.content); else if (this.o.content.parentNode) this.o.content.parentNode.removeChild(this.o.content);
    this.m = m;
  };
  CustomOverlay.prototype.getMap = function () { return this.m; };
  CustomOverlay.prototype.setPosition = function (p) { this.o.position = p; };
  CustomOverlay.prototype.setZIndex = function () {};
  CustomOverlay.prototype.setContent = function (n) { var p = this.o.content.parentNode; if (p) p.replaceChild(n, this.o.content); this.o.content = n; };
  function Shape() { return { setMap: function () {}, setPath: function () {} }; }
  window.kakao = { maps: { load: function (fn) { fn(); }, LatLng: LatLng, Coords: Coords, Map: Map, CustomOverlay: CustomOverlay,
    Polyline: Shape, Circle: Shape, event: { addListener: function () {}, removeListener: function () {} }, CopyrightPosition: { BOTTOMRIGHT: 1 } } };
})();
