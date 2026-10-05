// Sample project for the hunches UI kit: a layoffs corpus. Mock data only.
window.HD = (function () {
  var seeds = [
    'The author says they were laid off',
    'I lost my job in a round of layoffs',
    'My position was eliminated last week',
    'The author describes getting a severance package',
    'I was let go along with my whole team',
    'The author is worried they will be laid off next',
    'Rumours of layoffs at my company',
    'Our company announced a hiring freeze',
    'HR called me into a meeting and ended my contract',
    'The author is job hunting after a layoff',
    'I got the email that my role was cut',
    'The author describes the day they were fired',
  ];
  var labels = [
    { name: 'layoff_story', description: 'Author describes losing their own job', color: 'var(--label-1)' },
    { name: 'layoff_fear', description: 'Author worries about losing their job', color: 'var(--label-2)' },
    { name: 'hiring_freeze', description: "Author's employer stopped hiring", color: 'var(--label-3)' },
    { name: 'off_topic', description: '', color: 'var(--label-off)' },
  ];
  var texts = [
    'Got the 9am calendar invite from HR with no title. Twenty minutes later my laptop was locked. Eight years there.',
    'Everyone on my floor is whispering about cuts after the earnings call. I have a mortgage. Should I start applying now?',
    'Our VP said no new reqs until Q3 at the earliest, so the two open roles on my team are gone.',
    'Big tech layoffs continue: another 4,000 jobs cut, according to a filing this morning.',
    'They let my entire team go on Friday. Severance is 10 weeks. Not sure what to do next.',
    'Third round of layoffs this year. I survived again but I feel sick every Monday.',
    'My manager told me my position was eliminated. I trained my replacement last month.',
    'We were told hiring is paused company-wide, even backfills.',
    'Laid off in March, finally signed an offer today. Hang in there everyone.',
    'Leadership keeps saying the roadmap is "under review". I have seen this movie before.',
  ];
  var dis = [
    { text: 'My dad got laid off from the plant after 30 years and I do not know how to help him.', gold: ['off_topic'], pred: ['layoff_story'], reason: "The author's father was laid off, not the author. The post describes a layoff, so layoff_story was the closest label." },
    { text: 'Leadership keeps saying the roadmap is "under review". I have seen this movie before.', gold: ['layoff_fear'], pred: ['off_topic'], reason: "The post mentions a roadmap under review but never refers to jobs or layoffs, so no label applies." },
    { text: 'I was told my contract will not be renewed in June. Technically not a layoff?', gold: ['layoff_story'], pred: ['layoff_fear'], reason: "The author's contract will not be renewed, which reads as worry about losing the job rather than a layoff that happened." },
    { text: 'Company froze promotions and hiring. My review got pushed to next year.', gold: ['hiring_freeze'], pred: ['off_topic'], reason: "Promotions and hiring froze, but the post focuses on the author's delayed review, so it was treated as unrelated." },
    { text: 'Watching my friends get laid off one by one is brutal.', gold: ['off_topic'], pred: ['layoff_fear'], reason: "The author is distressed about friends being laid off, which reads as worry about layoffs in general." },
    { text: 'Took the voluntary redundancy package. Last day Friday.', gold: ['layoff_story'], pred: 'failed', error: 'UnexpectedModelBehavior: Exceeded maximum retries (1) for output validation' },
    { text: 'Our startup ran out of runway and the founders shut it down.', gold: ['layoff_story'], pred: ['off_topic'], reason: "The company shut down after running out of money. That is not a layoff or a hiring freeze at an employer." },
  ];
  var bands = [0.6, 0.625, 0.65, 0.675, 0.7, 0.725, 0.75];
  var bandCounts = [1204, 912, 640, 388, 246, 131, 91];
  var offTopic = [19, 12, 5, 3, 2, 1, 0];
  var results = [];
  for (var j = 0; j < 40; j++) {
    var multi = j % 9 === 4;
    var lab = [['layoff_story'], ['layoff_fear'], ['hiring_freeze'], ['layoff_story'], ['off_topic']][j % 5];
    results.push({ id: (0xa10000 + j * 104729).toString(16).slice(0, 6), sim: 0.98 - j * 0.0079, labels: multi ? ['layoff_story', 'hiring_freeze'] : lab, text: texts[(j * 3) % texts.length] });
  }
  var won = [[1050, 0], [702, 1], [540, 2], [395, 5], [288, 7], [207, 4], [150, 9], [110, 3], [78, 10], [52, 11], [25, 6], [15, 8]];
  var taxonomy = "mode: single\nlabels:\n- name: layoff_story\n  description: Author describes losing their own job\n- name: layoff_fear\n  description: Author worries about losing their job\n- name: hiring_freeze\n  description: Author's employer stopped hiring";
  var prompt = "# Classifier\nYou label one social media post.\n\n## Labels\n- layoff_story: the author lost their own job.\n- layoff_fear: the author worries they will.\n- hiring_freeze: the author's employer stopped hiring.\n- off_topic: the item matches none of the labels.\n\nReturn exactly one label.";
  var proposed = "# Classifier\nYou label one social media post.\n\n## Labels\n- layoff_story: the author lost their own job, including\n  contracts not renewed and voluntary redundancy.\n- layoff_fear: the author worries they will.\n- hiring_freeze: the author's employer stopped hiring.\n- off_topic: the item matches none of the labels. Layoffs\n  of friends, family or other companies are off_topic.\n\nReturn exactly one label.";
  var diff = "--- current\n+++ proposed\n@@ -4,7 +4,9 @@\n ## Labels\n-- layoff_story: the author lost their own job.\n+- layoff_story: the author lost their own job, including\n+  contracts not renewed and voluntary redundancy.\n - layoff_fear: the author worries they will.\n - hiring_freeze: the author's employer stopped hiring.\n-- off_topic: the item matches none of the labels.\n+- off_topic: the item matches none of the labels. Layoffs\n+  of friends, family or other companies are off_topic.";
  return {
    project: 'layoffs-2026', seeds: seeds, labels: labels, texts: texts, dis: dis, bands: bands, bandCounts: bandCounts, offTopic: offTopic, results: results,
    won: won, taxonomy: taxonomy, prompt: prompt, proposed: proposed, diff: diff,
    smart: 'anthropic:claude-sonnet-5-5', cheap: 'anthropic:claude-haiku-4-5', embed: 'openai:text-embedding-3-small',
  };
})();
window.fmt = function (n) { return n.toLocaleString('en-US'); };
window.labelColor = function (name) { var l = window.HD.labels.find(function (x) { return x.name === name; }); return l ? l.color : 'var(--label-off)'; };
