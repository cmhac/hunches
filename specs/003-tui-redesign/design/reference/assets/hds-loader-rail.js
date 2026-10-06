
// Rail design: loads components-rail/ overrides first, falling back to components/.
(function () {
  var FILES = ["frame/Terminal","frame/StatusHeader","frame/Rail","frame/Footer","layout/Panel","layout/Modal","data/DataTable","data/Bar","data/ProgressBar","data/Sparkline","data/Badge","data/LabelTag","data/Diff","chat/ChatPanel","forms/Input","forms/Button","forms/Select","forms/TextArea","forms/LabelOption","feedback/Notice","feedback/Toast"];
  window.loadHDS = async function (root) {
    var srcs = await Promise.all(FILES.map(async function (f) {
      var r = await fetch(root + 'components-rail/' + f + '.jsx');
      if (!r.ok) r = await fetch(root + 'components/' + f + '.jsx');
      return r.text();
    }));
    var code = srcs.map(function (s) { return s.replace(/^import .*$/mg, '').replace(/export (function|const)/g, '$1'); }).join('\n');
    var names = FILES.map(function (f) { return f.split('/')[1]; }).concat(['STAGES']);
    code += '\nwindow.HDS = {' + names.join(',') + '};';
    (0, eval)(Babel.transform(code, { presets: ['react'] }).code);
    return window.HDS;
  };
})();
