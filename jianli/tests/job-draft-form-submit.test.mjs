import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { transform } from "sucrase";
import { quoteStillMatches } from "../src/lib/job-draft.ts";

// Exercise the real submit function with a recording API, never a business request.
const source = fs.readFileSync(new URL("../src/components/JobForm.tsx", import.meta.url), "utf8");
const start = source.indexOf("  async function submit(");
const end = source.indexOf("  function updateRequirement(", start);
assert.ok(start >= 0 && end > start, "JobForm submit boundary must be explicit");
const body = transform(source.slice(start, end), { transforms: ["typescript"] }).code;
const prose = "负责开发企业业务接口并编写测试，能够使用Python分析数据和维护服务。";
const quote = "能够使用Python分析数据和维护服务";

for (const prefix of ["", "\uFEFF", "🚀"]) {
  for (const edit of [false, true]) {
    test(`actual ${edit ? "update" : "create"} preserves canonical text prefix ${JSON.stringify(prefix)}`, async () => {
      // U+FEFF is retained by the server's Pydantic/Python normalization, but JS trim removes it.
      const description = prefix + prose;
      const sourceStart = Array.from(description.slice(0, description.indexOf(quote))).length;
      const row = { rawText: quote, skillName: "Python", weight: 3, isRequired: true,
        sourceQuote: quote, sourceStart, sourceEnd: sourceStart + Array.from(quote).length };
      let sent;
      const errors = [];
      const context = { submitting: {current:false}, setError: e=>errors.push(e), setBusy: ()=>{},
        requirements:[row], description, enterpriseId:"synthetic-org", title:"synthetic-job",
        category:"software", city:"不限", employmentType:"internship", jobStatus:"draft",
        originalRequirements:{current:JSON.stringify([row])}, jobId:edit ? "synthetic-job" : undefined,
        organizations:[{id:"synthetic-org",name:"synthetic-company"}], quoteStillMatches,
        api:{createJob:async payload=>{sent=payload;return{id:"synthetic-job"};},
          updateJob:async (_id,payload)=>{sent=payload;return{id:"synthetic-job"};}},
        router:{push:()=>{},refresh:()=>{}}, errorMessage:e=>String(e) };
      const submit = Function(...Object.keys(context), `${body}; return submit;`)(...Object.values(context));
      await submit({preventDefault:()=>{}});
      assert.deepEqual(errors, [""]);
      assert.ok(sent, "real form submit must reach recording API");
      assert.equal(sent.description, description, "do not renormalize the canonical source on save");
      assert.equal(quoteStillMatches(sent.description, row), true);
    });
  }
}
