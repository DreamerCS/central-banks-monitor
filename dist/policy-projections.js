(() => {
  'use strict';
  const id = key => document.getElementById(key);
  const node = (tag,value) => {
    const n=document.createElement(tag);if(value!=null)n.textContent=value;return n;
  };
  const small = text => {const p=node('p',text);p.className='ce-small';return p;};
  const result=text=>{const p=node('p',text);p.className='study-result';return p;};
  const num = (v,places=2) => Number.isFinite(v) ? new Intl.NumberFormat('en-GB',{minimumFractionDigits:places,maximumFractionDigits:places}).format(v).replace('-','−') : '—';
  const signed = (v,places=2) => (v>0?'+':'')+num(v,places);
  const median = a => {
    const x=a.filter(Number.isFinite).sort((a,b)=>a-b), n=x.length;
    return n ? (x[Math.floor((n-1)/2)]+x[Math.floor(n/2)])/2 : null;
  };
  const ratio=(a,b)=>b?a+' / '+b+' ('+Math.round(100*a/b)+'%)':'—';
  function link(label,href){const a=node('a',label);a.href=href;return a;}
  function links(entries){const box=node('div');box.className='ce-links';for(const [label,url] of entries){if(url)box.append(link(label,url));}return box;}
  function table(title,headers,rows){
    const wrapper=node('div');wrapper.className='ce-tables';wrapper.tabIndex=0;wrapper.setAttribute('role','region');wrapper.setAttribute('aria-label',title);
    const t=node('table'),head=node('thead'),headrow=node('tr'),body=node('tbody');
    for(const s of headers){const th=node('th',s);th.scope='col';headrow.append(th);}
    for(const row of rows){const tr=node('tr');row.forEach((v,i)=>{const c=node(i?'td':'th',v);if(!i)c.scope='row';tr.append(c);});body.append(tr);}
    head.append(headrow);t.append(node('caption',title),head,body);wrapper.append(t);return wrapper;
  }
  function options(select,values,wanted){
    select.replaceChildren(...values.map(([key,label])=>new Option(label,key)));
    select.disabled=!values.length;select.value=values.some(([k])=>k===wanted)?wanted:(values.at(-1)?.[0]||'');
  }
  function scatter(rows,stage,date){
    const points=rows.filter(r=>Number.isFinite(r.fundsRevisionBp)&&Number.isFinite(r[stage+'Ois1yBp']));
    const fig=node('figure');fig.className='paired-fig';
    if(points.length<3)return fig;
    fig.append(node('figcaption','Change in year-end rate projection and the one-year OIS move'));
    const ns='http://www.w3.org/2000/svg';
    function add(tag,attrs,text){const e=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));if(text!=null)e.textContent=text;return e;}
    const chart=add('svg',{id:'fp-plot',viewBox:'0 0 620 220',role:'img','aria-label':'Horizontal axis shows the change in the median rate projection. Vertical axis shows the OIS change. The selected release is highlighted.'});
    const xVals=points.map(r=>r.fundsRevisionBp),yVals=points.map(r=>r[stage+'Ois1yBp']);
    const xmin=Math.floor(Math.min(-5,...xVals)/5)*5,xmax=Math.ceil(Math.max(5,...xVals)/5)*5;
    const ymin=Math.floor(Math.min(-1,...yVals)),ymax=Math.ceil(Math.max(1,...yVals));
    const X=v=>56+535*(v-xmin)/(xmax-xmin),Y=v=>167-135*(v-ymin)/(ymax-ymin);
    for(const v of [xmin,0,xmax])chart.append(add('line',{x1:X(v),x2:X(v),y1:29,y2:168,class:v===0?'zero':'axis'}),add('text',{x:X(v),y:185,'text-anchor':'middle'},v));
    for(const v of [ymin,0,ymax])chart.append(add('line',{x1:55,x2:593,y1:Y(v),y2:Y(v),class:v===0?'zero':'axis'}),add('text',{x:49,y:Y(v)+4,'text-anchor':'end'},v));
    chart.append(add('text',{x:54,y:16},'One-year OIS change (bp)'),add('text',{x:315,y:210,'text-anchor':'middle'},'Median projection revision (bp)'));
    for(const r of points.sort((a,b)=>(a.date===date)-(b.date===date))){const c=add('circle',{cx:X(r.fundsRevisionBp),cy:Y(r[stage+'Ois1yBp']),r:r.date===date?5:3.7,class:r.date===date?'selected':'point'});c.append(add('title',{},r.date+' · '+signed(r.fundsRevisionBp,0)+' bp projection, '+signed(r[stage+'Ois1yBp'])+' bp OIS'));chart.append(c);}
    fig.append(chart);return fig;
  }
  let fed=[],ecb=[],guidance;
  function fedView(){
    const h=id('fp-horizon').value, f=id('fp-frame').value,stage=id('fp-stage').value, select=id('fp-date');
    const rows=fed.filter(r=>r.horizon===h&&r.frame===f);
    if(!rows.length)return;
    options(select,rows.map(r=>[r.date,r.date+' · target '+r.targetYear]),select.value||(f==='historical'?'2023-12-13':''));
    const compare=rows.filter(r=>Number.isFinite(r.fundsRevisionBp));
    const by=[[-1,'Median lowered'],[0,'Median unchanged'],[1,'Median raised']].map(([direction,label])=>{
      const g=compare.filter(r=>Math.sign(r.fundsRevisionBp)===direction),valid=g.filter(r=>Number.isFinite(r[stage+'Ois1yBp']));
      const mat=valid.filter(r=>Math.abs(r[stage+'Ois1yBp'])>1);
      return [label,g.length,valid.length,signed(median(valid.map(r=>r[stage+'Ois1yBp']))),direction?ratio(mat.filter(r=>Math.sign(r[stage+'Ois1yBp'])===direction).length,mat.length):'—'];
    });
    const selected=rows.find(r=>r.date===select.value);
    const material=compare.filter(r=>r.fundsRevisionBp!==0 && Math.abs(r[stage+'Ois1yBp'])>1);
    const aligned=material.filter(r=>Math.sign(r.fundsRevisionBp)===Math.sign(r[stage+'Ois1yBp'])).length;
    const message=material.length?'One-year OIS moved in the direction of the median rate revision on '+aligned+' of '+material.length+' meetings where the projection changed and OIS moved more than 1 bp.':'No meeting in this selection had both a change in the median rate projection and a one-year OIS move larger than 1 bp.';
    id('fp-summary').replaceChildren(result(message),scatter(compare,stage,selected.date),table('One-year OIS by direction of the median policy-rate revision',['Fixed-year rate projection','Meetings','OIS quotes','Median OIS move (bp)','Same direction when |OIS| >1 bp'],by));
    const fields=[['funds','Year-end federal funds rate','bp'],['growth','Real GDP growth','pp'],['inflation','PCE inflation','pp'],['core','Core PCE inflation','pp'],['unemployment','Unemployment rate','pp']];
    id('fp-case').replaceChildren(table(selected.date+' projections for '+selected.targetYear,['FOMC median','Prior release (%)','New release (%)','Revision'],fields.map(([k,label,unit])=>[label,num(selected[k+'PreviousPct'],1),num(selected[k+'MedianPct'],1),signed(selected[k+(k==='funds'?'RevisionBp':'RevisionPp')],k==='funds'?0:1)+' '+unit])),
      table('Same meeting, two market windows',['Window','One-year OIS (bp)','US 2Y (bp)','US 2s10s (bp)','S&P 500 (%)'],['release','conference'].map(k=>[k==='release'?'Statement':'Press conference',...['Ois1yBp','Yield2yBp','Slope2s10sBp','EquityPct'].map(a=>signed(selected[k+a]))])),
      links([['Official projection table',selected.projectionSource],['Market observations','cross-asset-events.html?bank=fed&stage=release&event=fed-'+selected.date+'-release']]));
  }
  function ecbView(){
    const h=id('ep-horizon').value,period=id('ep-frame').value,select=id('ep-date');
    const publicOnly=id('ep-public').value==='public';
    const rows=ecb.filter(r=>r.horizon===h&&(!publicOnly||r.publicAtVintage&&r.previousPublicAtVintage)&&(period==='all'||(period==='early'?r.vintage<'2010':period==='mid'?r.vintage>='2010'&&r.vintage<'2020':r.vintage>='2020')));
    if(!rows.length)return;
    options(select,rows.map(r=>[r.vintage,r.vintage+' · target '+r.targetYear]),select.value||'2022-09');
    const paired=rows.filter(r=>Number.isFinite(r.hicpRevisionPp)&&Number.isFinite(r.gdpRevisionPp));
    const grid=[1,0,-1].map(i=>[[ 'Inflation down','Inflation unchanged','Inflation up'][i+1],...[-1,0,1].map(g=>paired.filter(r=>Math.sign(r.hicpRevisionPp)===i&&Math.sign(r.gdpRevisionPp)===g).length)]);
    const divergent=paired.filter(r=>r.hicpRevisionPp>0 && r.gdpRevisionPp<0).length;
    id('ep-summary').replaceChildren(result('Staff raised projected inflation and cut projected growth in '+divergent+' of '+paired.length+' comparable rounds for the selected target year.'),small(paired.length+' of '+rows.length+' vintages have both revisions against the preceding round for the same target year. Each comparable round appears once in the table.'),table('Joint revisions to annual euro-area projections (number of vintages)',['HICP revision','GDP down','GDP unchanged','GDP up'],grid));
    const r=rows.find(r=>r.vintage===select.value);
    id('ep-case').replaceChildren(table(r.vintage+' forecasts for '+r.targetYear,['Measure','Prior round (%)','Selected round (%)','Revision (pp)','Selected-round basis'],[['HICP inflation',num(r.previousHicpPct,2),num(r.hicpPct,2),signed(r.hicpRevisionPp),r.hicpBasis],['Real GDP growth',num(r.previousGdpPct,2),num(r.gdpPct,2),signed(r.gdpRevisionPp),r.gdpBasis]]),
      small('Previous vintage '+(r.previousVintage||'unavailable')+'. The selected round was '+(r.publicAtVintage?'public at the time.':'an internal exercise at the time.')), links([['Published projection table',r.tableUrl],['ECB inflation series',r.hicpSeriesUrl],['ECB GDP series',r.gdpSeriesUrl]]));
  }
  function guidanceView(){
    const panel=id('tg-panel'),select=id('tg-sample');
    if(!guidance?.panels?.length)return;
    options(panel,guidance.panels.map(p=>[p.id,p.label]),panel.value||'fedRelease');
    const p=guidance.panels.find(r=>r.id===panel.value);
    options(select,p.variants.map(v=>[v.id,v.label]),select.value||'all');
    const v=p.variants.find(i=>i.id===select.value);
    const rows=v.groups.map(g=>[({tighter:'Tighter',easier:'Easier',unchanged:'Unchanged'})[g.direction]||g.direction,g.nText,g.nOis,signed(g.medianOisBp),signed(g.medianSlopeBp),signed(g.medianEquityPct),g.direction==='unchanged'?'—':ratio(g.alignedN,g.materialN)]);
    id('tg-summary').replaceChildren(small(p.nPaired+' of '+p.nEvents+' documents in this panel have an adjacent comparable text score. '+p.nMissingShift+' lack a comparable change. Each asset uses the available observations in the selected window.'),
      table(v.label+' · market movement by change in text score',['Change in guidance','Scored pairs','OIS quotes','Median OIS (bp)','Median 2s10s (bp)','Median equity (%)','Same direction when |OIS| >1 bp'],rows),
      small('An unchanged score can accompany a market move. Statements also disclose the economic outlook and contemporaneous decisions. The sparse counts for directional guidance limit comparisons.'));
  }
  async function load(file){
    const response=await fetch('data/'+file+'.json');
    if(!response.ok)throw new Error('Unavailable');return response.json();
  }
  function assign(keys,fn){for(const k of keys)id(k).addEventListener('change',fn);}
  assign(['fp-horizon','fp-stage','fp-frame','fp-date'],fedView);
  assign(['ep-horizon','ep-frame','ep-public','ep-date'],ecbView);assign(['tg-panel','tg-sample'],guidanceView);
  load('fed-projection-vintages').then(data=>{fed=data;fedView();}).catch(()=>id('fp-summary').replaceChildren(small('The projection data are unavailable. The CSV is linked below.')));
  load('ecb-projection-vintages').then(data=>{ecb=data.records;ecbView();}).catch(()=>id('ep-summary').replaceChildren(small('The vintage data are unavailable. The CSV is linked below.')));
  load('guidance-market-test').then(data=>{guidance=data;guidanceView();}).catch(()=>id('tg-summary').replaceChildren(small('The guidance data are unavailable. The CSV is linked below.')));
})();
