import{x as b,d as f,o as i,c as m,n as d,j as v,q as w,E as u,t as o,m as _,N as k,b as e,O as C,y as M,u as j,p as B,f as s,e as l,g as h,F as z,r as H}from"./index-DDP-zX5t.js";import{F as I}from"./file-text-C9eHdypY.js";import{C as g}from"./chevron-left-BvblI_tc.js";import{M as N}from"./message-circle-CO2lxXCh.js";/**
 * @license lucide-vue-next v0.344.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const y=b("BookIcon",[["path",{d:"M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20",key:"t4utmx"}]]);/**
 * @license lucide-vue-next v0.344.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=b("CopyIcon",[["rect",{width:"14",height:"14",x:"8",y:"8",rx:"2",ry:"2",key:"17jyea"}],["path",{d:"M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2",key:"zix9uf"}]]);/**
 * @license lucide-vue-next v0.344.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=b("HeartIcon",[["path",{d:"M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z",key:"c3ymky"}]]);/**
 * @license lucide-vue-next v0.344.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const S=b("TagIcon",[["path",{d:"M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z",key:"vktsd0"}],["circle",{cx:"7.5",cy:"7.5",r:".5",fill:"currentColor",key:"kqv944"}]]),V=f({__name:"StatusTag",props:{type:{},label:{}},setup(n){const x=n,r=_(()=>{switch(x.type){case"manual":return{icon:y,label:"手册",cls:"bg-primary/10 text-primary"};case"case":return{icon:I,label:"案例",cls:"bg-accent/10 text-accent"};case"graph":return{icon:k,label:"图谱",cls:"bg-ai/10 text-ai"};default:return{icon:S,label:x.label||"标签",cls:"bg-text-2/10 text-text-2"}}});return(c,a)=>(i(),m("span",{class:d(["inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium",r.value.cls])},[(i(),v(w(r.value.icon),{class:"w-3 h-3"})),u(" "+o(x.label||r.value.label),1)],2))}}),$={class:"flex items-center gap-2 w-full"},A=f({__name:"SimilarityBar",props:{value:{},size:{}},setup(n){return(x,r)=>(i(),m("div",$,[e("div",{class:d(["flex-1 bg-border rounded-full overflow-hidden",n.size==="sm"?"h-1.5":"h-2"])},[e("div",{class:"h-full bg-accent transition-[width] duration-500",style:C({width:Math.max(0,Math.min(1,n.value))*100+"%"})},null,4)],2),e("span",{class:d(["mono text-xs tabular-nums w-10 text-right",n.value>=.8?"text-accent font-semibold":"text-text-2"])},o(Math.round(Math.max(0,Math.min(1,n.value))*100))+"% ",3)]))}}),F={key:0,class:"flex-shrink-0 h-12 bg-card border-b border-border flex items-center px-2"},L={class:"flex-1 text-center font-semibold truncate"},O={class:"flex flex-wrap items-start gap-3 mb-4"},E={class:"text-xl md:text-2xl font-bold flex-1 min-w-0"},K={class:"w-44"},P={class:"text-sm text-text-2 flex items-center gap-3 flex-wrap"},q={class:"inline-flex items-center gap-1"},R={class:"mono px-2 py-0.5 rounded bg-bg"},Y={class:"mt-6 leading-7 whitespace-pre-wrap"},Z={class:"mt-5 grid grid-cols-3 gap-2"},G={class:"mt-6 pt-4 border-t border-border flex items-center gap-3 text-sm"},J={class:"ml-auto text-xs text-text-2 mono"},Q={class:"flex-1 h-10 rounded-btn bg-bg flex items-center justify-center gap-1 text-sm"},U={class:"flex-1 h-10 rounded-btn bg-bg flex items-center justify-center gap-1 text-sm"},W={class:"flex-1 h-10 rounded-btn bg-accent text-white flex items-center justify-center gap-1 text-sm font-semibold"},oe=f({__name:"Detail",setup(n){const x=M(),r=j(),{isPC:c}=B(),a={id:x.params.id,title:"热轧主电机异响处理案例 #2024-031",type:"case",similarity:.92,source:"王师傅提交 · 2024-03-15",device:"YKK630-4",body:`### 故障现象
检修员发现主电机驱动端轴承温度异常上升至 78℃,伴随金属摩擦声,持续约 4 小时。

### 处理过程
1. 立即按 SOP §4.3 流程停机,执行 LOTO 锁定
2. 等待电机自然冷却至 40℃ 以下,使用红外测温仪复测
3. 拆卸驱动端端盖,目视检查滚动体与保持架
4. 发现保持架轻微变形,滚动体表面有点蚀剥落
5. 更换轴承,清洗轴承腔,填充 Mobil Polyrex EM 润滑脂
6. 装复后通电试运行 10 分钟,振动速度 3.2mm/s,温升 28K,无异响

### 经验总结
- 轴承点蚀往往与润滑脂污染或寿命到期有关
- 建议建立按里程的预防性更换制度
- 拆卸时务必使用专用拉马,严禁锤击`};return(X,t)=>(i(),m("div",{class:d(s(c)?"p-6 max-w-5xl mx-auto":"h-full flex flex-col")},[s(c)?h("",!0):(i(),m("header",F,[e("button",{onClick:t[0]||(t[0]=p=>s(r).back()),class:"w-10 h-10 flex items-center justify-center"},[l(s(g),{class:"w-5 h-5"})]),e("span",L,o(a.title),1),t[2]||(t[2]=e("span",{class:"w-10"},null,-1))])),e("div",{class:d(s(c)?"":"flex-1 overflow-auto")},[e("div",{class:d(["industrial-card p-6",s(c)?"":"rounded-none border-x-0"])},[s(c)?(i(),m("button",{key:0,onClick:t[1]||(t[1]=p=>s(r).back()),class:"text-sm text-text-2 hover:text-accent mb-3 inline-flex items-center gap-1"},[l(s(g),{class:"w-4 h-4"}),t[3]||(t[3]=u(" 返回结果列表 ",-1))])):h("",!0),e("div",O,[l(V,{type:a.type},null,8,["type"]),e("h1",E,o(a.title),1),e("div",K,[t[4]||(t[4]=e("div",{class:"text-xs text-text-2 mb-1"},"相似度",-1)),l(A,{value:a.similarity},null,8,["value"])])]),e("div",P,[e("span",q,[l(s(y),{class:"w-3.5 h-3.5"}),u(o(a.source),1)]),e("span",R,o(a.device),1)]),e("article",Y,o(a.body),1),e("div",Z,[(i(),m(z,null,H(3,p=>e("div",{key:p,class:"aspect-video bg-bg rounded-card border border-border flex items-center justify-center text-text-2 text-xs"},"现场照片 "+o(p),1)),64))]),e("div",G,[t[5]||(t[5]=e("button",{class:"text-text-2 hover:text-success"},"👍 有帮助",-1)),t[6]||(t[6]=e("button",{class:"text-text-2 hover:text-danger"},"👎 不准确",-1)),e("span",J,"案例 ID: "+o(a.id),1)])],2)],2),e("footer",{class:d(["flex-shrink-0 h-14 border-t border-border bg-card flex items-center px-3 gap-2",s(c)?"mt-4 industrial-card !h-14 px-4":"safe-bottom"])},[e("button",Q,[l(s(D),{class:"w-4 h-4"}),t[7]||(t[7]=u(" 收藏",-1))]),e("button",U,[l(s(T),{class:"w-4 h-4"}),t[8]||(t[8]=u(" 复制",-1))]),e("button",W,[l(s(N),{class:"w-4 h-4"}),t[9]||(t[9]=u(" 以此继续提问 ",-1))])],2)],2))}});export{oe as default};
