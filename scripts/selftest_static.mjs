// JS 轻量引擎 vs Python 官方快照 对齐自检
import { readFileSync } from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { Engine } = require('./engine.js');
const cfg = JSON.parse(readFileSync('data/engine_config.json', 'utf8'));
const emp = JSON.parse(readFileSync('data/employees.json', 'utf8'));
const presets = JSON.parse(readFileSync('data/presets.json', 'utf8'));
const jobsText = readFileSync('../data/jobs/blind_gold_jobs.json', 'utf8') + readFileSync('../data/jobs/blind_gold_jobs_batch2.json', 'utf8') + readFileSync('../data/jobs/agent_blind_jobs_v1.json', 'utf8');
Engine.loadConfig(cfg);
// presets 没带完整 JD 文本——从源文件拼
const allJobs = [...JSON.parse(readFileSync('../data/jobs/blind_gold_jobs.json', 'utf8')).jobs,
                 ...JSON.parse(readFileSync('../data/jobs/blind_gold_jobs_batch2.json', 'utf8')).jobs,
                 ...JSON.parse(readFileSync('../data/jobs/agent_blind_jobs_v1.json', 'utf8')).jobs];
let tot5 = 0, n = 0;
for (const p of presets.slice(0, 15)) {
  const job = allJobs.find((j) => j.job_id === p.job_id);
  const { results } = Engine.score(job.job_type, job, emp);
  const jsTop5 = results.slice(0, 5).map((r) => r.id);
  const pyTop5 = p.top.slice(0, 5).map((t) => t.id);
  const overlap = jsTop5.filter((x) => pyTop5.includes(x)).length;
  tot5 += overlap; n += 1;
  const py1 = pyTop5[0], jsRank1 = results.findIndex((r) => r.id === py1) + 1;
  console.log(`${p.job_id} Top5重合 ${overlap}/5｜Python#1 ${py1} 在JS第 ${jsRank1} 名`);
}
console.log(`\n平均 Top5 重合：${(tot5 / n).toFixed(2)}/5`);
