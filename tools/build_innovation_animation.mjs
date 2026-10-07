import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {Presentation, PresentationFile} from '@oai/artifact-tool';

const root=process.cwd();
const buildDir=path.join(root,'output/innovation-animation-20261007');
const sourceDir=path.join(root,'docs/submission/figures/innovation-details-20261007');
await fs.mkdir(buildDir,{recursive:true});
const font='Microsoft YaHei';
const sourceSize={width:1672,height:941};
const part=(name,rect,row,col)=>({name,rect,row,col});
const columns=(names,xs,y0,y1,row)=>names.map((name,i)=>part(name,[xs[i],y0,xs[i+1],y1],row,i));
const slides=[
 {title:'受约束的研究定义生成',file:'01-constrained-method-definition.png',roi:[0,200,1672,735],
  parts:columns(['研究描述','意图解析','字段与算子目录','指标与观察定义','用户确认','确定性程序计算','计算结果'],[0,190,400,690,1145,1310,1515,1672],200,735,0),
  notes:'自然语言或明确语义规则提出目录内定义草稿。引用与依赖校验通过后，用户确认保存。主体、期间、单位与分母检查在程序执行时进行。示意数据：20万元净利润除以100万元营业收入，净利率为20%。CALCULATED不等于事实已验证。实现依据：app/service/research_method_builder.py；app/service/personal_research.py。'},
 {title:'内容指纹驱动的变化记录',file:'02-content-fingerprint-events.png',roi:[0,35,1672,890],
  parts:[part('上次复核',[0,35,355,455],0,0),part('内容指纹生成',[355,35,825,890],0,1),part('指纹比较',[825,35,1050,890],0,2),part('相同内容处理',[1050,35,1672,455],0,3),part('本次复核',[0,455,355,890],1,0),part('变化事件记录',[1050,455,1672,890],1,3)],
  notes:'复核指纹覆盖配置、状态、来源与指标值。相同内容仍更新复核时间，不新增变化事件。不同内容记录事件。H1、H2为符号标识。资料不足与方法版本变化保留明确状态。实现依据：app/service/investment_hypotheses.py；app/service/research_lab_store.py。'},
 {title:'公告主体与持仓敞口关联',file:'03-announcement-exposure-paths.png',roi:[10,5,1662,900],
  parts:[part('公告主体',[10,5,350,390],0,0),part('直接持仓',[350,5,650,450],0,1),part('公司主体关联',[650,5,1000,450],0,2),part('敞口汇合路径',[1000,5,1280,900],0,3),part('已知敞口结果',[1280,5,1662,900],0,4),part('基金披露与残余',[10,390,350,900],1,0),part('成分穿透',[350,450,650,900],1,1),part('间接敞口',[650,450,1000,650],1,2),part('未穿透残余',[650,650,1000,900],2,2)],
  notes:'示意组合为直接持仓10000元与ETF10000元。ETF披露公司A占基金10%，间接敞口1000元，直接和间接合计11000元，占总资产55%。未披露90%即9000元单列，不外推。公告文本变化不表示股价因果。实现依据：app/service/announcement_impact.py；app/portfolio/exposure.py。'},
 {title:'风险检查后的虚拟账本更新',file:'04-gated-virtual-ledger.png',roi:[0,50,1672,880],
  parts:[part('共同报价与费用',[270,50,1672,240],0,0),part('同一初始基线',[0,50,270,880],1,0),
   ...columns(['策略A定义','策略A条件与目标','策略A调仓测算','策略A完整检查','策略A应用动作','策略A虚拟账本'],[270,535,705,865,1225,1340,1672],240,540,1).map(p=>({...p,col:p.col+1})),
   ...columns(['策略B定义','策略B条件与目标','策略B调仓测算','策略B完整检查','策略B拦截边界','策略B保留账本'],[270,535,705,865,1260,1370,1672],540,880,2).map(p=>({...p,col:p.col+1}))],
  notes:'策略共享基线、报价和费用条件，各自保留虚拟账本。指标条件选择目标，复用调仓服务。调仓规则、组合体检、完整风险预算及现金数量条件共同控制是否应用交易。未通过时保留数量和现金，报价变化仍可改变估值。三个检查阶段不是风险与合规双闸门的替代名称。只记录前向虚拟测算，不提交真实订单。实现依据：app/service/shadow_portfolios.py；app/service/portfolio_rebalancing.py。'},
 {title:'按日期分配同一资金池',file:'05-dated-funding-pool.png',roi:[55,75,1650,875],
  parts:[...columns(['初始现金','当前分配与余额','近期需求与缺口','未来资金时间约束','到期收入与余额'],[55,410,645,1000,1260,1650],75,755,0),part('资金日期时间轴',[55,755,1650,875],1,0)],
  notes:'示意数据：2026年10月7日初始现金30000元，10月8日需求40000元分配30000元，近期缺口10000元，分配后余额0元。11月7日确认收入20000元到期入池，后续可用余额20000元。未来收入不提前使用，不追溯消除已记录近期缺口，同一笔资金只分配一次。实现依据：app/service/funding_goals.py。'}
];
function validateCoverage(spec){
 const [x0,y0,x1,y1]=spec.roi;
 let area=0;
 for(const p of spec.parts){
  const [a,b,c,d]=p.rect;
  assert(a>=x0&&b>=y0&&c<=x1&&d<=y1&&c>a&&d>b);
  area+=(c-a)*(d-b);
 }
 for(let i=0;i<spec.parts.length;i++)for(let j=i+1;j<spec.parts.length;j++){
  const a=spec.parts[i].rect,b=spec.parts[j].rect;
  assert(Math.max(a[0],b[0])>=Math.min(a[2],b[2])||Math.max(a[1],b[1])>=Math.min(a[3],b[3]),'Overlapping source regions');
 }
 assert.equal(area,(x1-x0)*(y1-y0),'Incomplete source coverage');
}
const deck=Presentation.create({slideSize:{width:1280,height:720}});
const metadata=[];
for(const [index,spec] of slides.entries()){
 validateCoverage(spec);
 const slide=deck.slides.add();
 slide.background.fill={type:'gradient',gradientKind:'linear',angleDeg:90,stops:[{offset:0,color:'#E9F3FF'},{offset:17000,color:'#FFFFFF'},{offset:100000,color:'#FFFFFF'}]};
 const title=slide.shapes.add({geometry:'textbox',name:'slide-title',position:{left:48,top:32,width:1184,height:68},fill:'none',line:{fill:'none',width:0}});
 title.text=spec.title;
 title.text.style={typeface:font,fontSize:43,bold:true,color:'#184A7A',autoFit:'none',insets:{left:0,right:0,top:0,bottom:0},verticalAlignment:'middle'};
 const bytes=await fs.readFile(path.join(sourceDir,spec.file));
 const [x0,y0,x1,y1]=spec.roi;
 const scale=Math.min(1184/(x1-x0),546/(y1-y0));
 const left=(1280-(x1-x0)*scale)/2,top=130+(546-(y1-y0)*scale)/2;
 const ordered=spec.parts.slice().sort((a,b)=>a.row-b.row||a.col-b.col);
 const pieces=[];
 for(const [j,p] of ordered.entries()){
  const [a,b,c,d]=p.rect;
  const bounds={left:left+(a-x0)*scale,top:top+(b-y0)*scale,width:(c-a)*scale,height:(d-b)*scale};
  slide.images.add({blob:bytes,contentType:'image/png',alt:p.name,fit:'cover',geometry:'rect',
   position:bounds,crop:{left:a/sourceSize.width,top:b/sourceSize.height,right:1-c/sourceSize.width,bottom:1-d/sourceSize.height}});
  pieces.push({name:p.name,row:p.row,col:p.col,sourceRect:p.rect,bounds,animationOrder:j+2});
 }
 slide.speakerNotes.textFrame.setText(spec.notes+'\n来源图片：docs/submission/figures/innovation-details-20261007/'+spec.file+'。');
 metadata.push({slide:index+1,title:spec.title,source:spec.file,roi:spec.roi,pieces,shapeCount:ordered.length+1});
}
await (await PresentationFile.exportPptx(deck)).save(path.join(buildDir,'candidate.pptx'));
await fs.writeFile(path.join(buildDir,'parts-manifest.json'),JSON.stringify({slides:metadata,font,slideSize:{width:1280,height:720},fadeDuration:0.4,delay:0.06},null,2));
console.log(JSON.stringify({slides:slides.length,pictureParts:metadata.reduce((s,m)=>s+m.pieces.length,0),candidate:path.join(buildDir,'candidate.pptx')}));
