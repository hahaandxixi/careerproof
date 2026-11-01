import test from "node:test";
import assert from "node:assert/strict";
import {displayIdentity,identityLabel} from "../src/lib/demo-display-identity.js";
test("only registered identities get aliases; name keywords never establish example status",()=>{
 for(const name of ["首页验收学生（合成）","Python 实现材料学生（合成）","真实姓名","小江"]){
  assert.deepEqual(displayIdentity(name,"unregistered"),{name,originalName:name,isExample:false});
  assert.equal(identityLabel(name,undefined),name);
 }
});
test("registered user ids drive display names; application ids are never identity keys",()=>{
 const userId="b5ec33cb-c669-4ae5-8a86-c1a591f5d2de";
 assert.equal(displayIdentity("原始姓名",userId).name,"林同学");assert.equal(identityLabel("原始姓名",userId),"林同学 · 示例");
 for(const applicationId of ["3724815b-78c4-4229-b98a-80da1ab00209","new-application"])assert.equal(displayIdentity("原始姓名",applicationId).isExample,false);
 assert.equal(displayIdentity("原始姓名","3e1e80a0-c7e0-4203-9aa9-f770b7ba3fe3").name,"陈同学");
 assert.equal(displayIdentity("原始姓名","a12657c4-48d1-436c-96c9-857243294838").name,"周同学");
});
