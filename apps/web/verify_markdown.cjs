const { marked } = require('marked');

function preprocessInlinePunctuation(text) {
  return text.replace(
    /(\*\*|__|\*|_)([^*_\n]+?)([：:、，。；;！？?!])(\*\*|__|\*|_)/g,
    '$1$2$4$3',
  );
}

const cases = [
  '**现象：**TMP更新XML文件成功',
  '**现象：**TMP更新XML文件成功，预览的也是一样的**现象：**TMP更新XML文件成功',
  '**注意：**这是提示内容',
  '**标签：**设备黑屏',
  '__说明：__见下文',
  '*要点：*请记住',
  '**现象**：正常写法（不应被破坏）',
  '**加粗**内容无冒号（不应被破坏）',
];

let pass = 0;
let fail = 0;
for (const c of cases) {
  const out = marked.parse(preprocessInlinePunctuation(c)).replace(/\n/g, '');
  console.log('IN : ' + c);
  console.log('OUT: ' + out);
  console.log('---');
}

// 断言
console.log('=== ASSERTIONS ===');
function assert(name, cond) {
  if (cond) { console.log('  [PASS] ' + name); pass++; }
  else { console.log('  [FAIL] ' + name); fail++; }
}

const r1 = marked.parse(preprocessInlinePunctuation('**现象：**TMP更新XML文件成功'));
assert('冒号移出加粗标记', r1.includes('<strong>现象</strong>') && r1.includes('：TMP'));

const r2 = marked.parse(preprocessInlinePunctuation('**现象：**TMP，预览也一样**现象：**TMP'));
assert('多次出现均修复', (r2.match(/<strong>现象<\/strong>/g) || []).length === 2);

const r3 = marked.parse(preprocessInlinePunctuation('**现象**：正常写法'));
assert('正常写法不破坏', r3.includes('<strong>现象</strong>：正常写法'));

const r4 = marked.parse(preprocessInlinePunctuation('**加粗**无冒号'));
assert('无标点加粗不破坏', r4.includes('<strong>加粗</strong>无冒号'));

console.log();
console.log('RESULT: ' + pass + ' passed, ' + fail + ' failed');
