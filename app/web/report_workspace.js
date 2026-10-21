/* Report preparation/lifecycle UI; extraction, saves and Word stay in HRS. */
(function(root){
'use strict';
async function choose({modal,topics,selected,reports,total=reports.length,nextOffset=null,listMore,manage}){
 let choice=selected?'topic:'+selected:'whole';
 return modal({title:'准备工程报告',kicker:'Word · 先查看工程效果',
  note:'进入独立临时工程稿后检查、修改和导出。原台账保持不变；已有稿按时间区分，可归档或移入可恢复的回收站。',
  okText:'进入工程工作页',
  body:outer=>{
   const group=document.createElement('div');group.className='report-scope-picker';
   function option(value,title,detail=''){
    const label=document.createElement('label'),radio=document.createElement('input'),text=document.createElement('span');
    radio.type='radio';radio.name='report-scope';radio.value=value;radio.checked=value===choice;radio.onchange=()=>{choice=value;};
    text.textContent=title;if(detail){const small=document.createElement('small');small.textContent=detail;small.className='modal-help';text.append(small);}
    label.append(radio,text);group.append(label);return label;
   }
   option('whole','整份文稿');topics.forEach(t=>option('topic:'+t.key,t.title));
   const tools=document.createElement('div'),showAll=document.createElement('button'),more=document.createElement('button'),status=document.createElement('p');
   showAll.type=more.type='button';showAll.className=more.className='btn btn-quiet';showAll.textContent='查看归档和回收站';more.textContent='加载更多临时稿';
   status.className='modal-help';let includeAll=false,offset=nextOffset,rows=[];
   function draw(items,append=false){
    if(!append){rows.forEach(n=>n.remove());rows=[];}
    for(const report of items){
     const date=new Date(report.updated).toLocaleString('zh-CN'),state=report.state==='archived'?'已归档':report.state==='trashed'?'回收站':'可继续';
     const row=option('resume:'+report.document_id,'临时稿：'+report.title,
      state+' · '+date+' · '+Math.ceil(report.bytes/1024)+' KB · '+(report.source_current===false?'来源已变化，此稿保留原快照':'当前来源快照'));
     rows.push(row);row.querySelector('input').disabled=report.state==='trashed';
     const actions=document.createElement('span');actions.className='workspace-row-actions';
     for(const [action,label] of report.state==='trashed'?[['restore','恢复']]:[['resume','打开'],[report.state==='archived'?'unarchive':'archive',report.state==='archived'?'取消归档':'归档'],['trash','移入回收站']]){
      const button=document.createElement('button');button.type='button';button.textContent=label;button.className='btn btn-quiet';
      button.onclick=async event=>{event.preventDefault();event.stopPropagation();
       if(action==='resume'){choice='resume:'+report.document_id;row.querySelector('input').checked=true;return;}
       button.disabled=true;
       try{await manage(report,action);const data=await listMore(0,includeAll);offset=data.next_offset;total=data.total;draw(data.reports);sync();}
       catch(error){status.textContent=error.message;}finally{button.disabled=false;}
      };actions.append(button);
     }
     row.append(actions);
    }
   }
   function sync(){more.hidden=offset===null;status.textContent='共 '+total+' 份临时稿；归档和回收不会删除附件或恢复草稿。';}
   more.onclick=async()=>{more.disabled=true;try{const data=await listMore(offset,includeAll);offset=data.next_offset;total=data.total;draw(data.reports,true);sync();}catch(error){status.textContent=error.message;}finally{more.disabled=false;}};
   showAll.onclick=async()=>{showAll.disabled=true;try{includeAll=!includeAll;const data=await listMore(0,includeAll);offset=data.next_offset;total=data.total;draw(data.reports);showAll.textContent=includeAll?'只看活动临时稿':'查看归档和回收站';sync();}catch(error){status.textContent=error.message;}finally{showAll.disabled=false;}};
   tools.append(showAll,more);outer.append(group,tools,status);draw(reports);sync();
  },onOk:()=>{const selected=document.querySelector('input[name="report-scope"]:checked');if(!selected||selected.disabled)throw Error('请选择范围或一个可继续的临时稿');return selected.value;}});
}
async function createJob(request,context,{progress,cancelButton}){
 const headers={'X-HRS-Project-Action':'user-action'},api=root.ReportOperations.request;
 const owner={document_id:context.document_id,draft_id:context.draft_id,template:context.template};
 const started=await api('/api/report-workspace','POST',{...context,...request,action:'start'},headers);
 let cancelling=false;
 cancelButton.hidden=false;cancelButton.disabled=false;
 cancelButton.onclick=async()=>{cancelling=true;cancelButton.disabled=true;progress.textContent='正在取消并清理…';
  try{await api('/api/report-workspace','POST',{...owner,action:'cancel',job_token:started.job_token},headers);}catch(error){progress.textContent='取消请求未确认：'+error.message+'；正在查询任务状态';}};
 try{
  while(true){
   const status=await api('/api/report-workspace','POST',{...owner,action:'status',job_token:started.job_token},headers,{timeout:30000});
   if(status.state==='completed')return status.result;
   if(status.state==='failed'||status.state==='cancelled')throw Error(status.error||'操作未完成');
   if(!cancelling)progress.textContent=status.phase+(status.bytes_total?' · '+Math.round(status.bytes_done/status.bytes_total*100)+'%':'');
   await new Promise(resolve=>setTimeout(resolve,180));
  }
 }finally{cancelButton.hidden=true;cancelButton.onclick=null;}
}
root.ReportWorkspace={choose,createJob};
})(window);
