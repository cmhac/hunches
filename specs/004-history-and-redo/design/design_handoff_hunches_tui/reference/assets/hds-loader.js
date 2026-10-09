// Loads the hunches components for cards and UI kits. Uses the compiled bundle namespace if present,
// otherwise fetches the .jsx sources and transpiles them in one shared scope.
(function () {
  var FILES = ["frame/Terminal","frame/StatusHeader","frame/Footer","layout/Panel","layout/Modal","data/DataTable","data/Bar","data/ProgressBar","data/Sparkline","data/Badge","data/LabelTag","data/Diff","chat/ChatPanel","forms/Input","forms/Button","forms/Select","forms/TextArea","forms/LabelOption","feedback/Notice","feedback/Toast"];
  window.loadHDS = async function (root) {
    if (window.HunchesDesignSystem && window.HunchesDesignSystem.Terminal) return window.HunchesDesignSystem;
    var srcs = await Promise.all(FILES.map(function (f) { return fetch(root + 'components/' + f + '.jsx').then(function (r) { return r.text(); }); }));
    var code = srcs.map(function (s) { return s.replace(/^import .*$/mg, '').replace(/export (function|const)/g, '$1'); }).join('\n');
    var names = FILES.map(function (f) { return f.split('/')[1]; }).concat(['STAGES']);
    code += '\nwindow.HDS = {' + names.join(',') + '};';
    (0, eval)(Babel.transform(code, { presets: ['react'] }).code);
    return window.HDS;
  };
})();
