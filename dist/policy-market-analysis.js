(() => {
  'use strict';
  const el=(tag,text,className)=>{
    const node=document.createElement(tag);
    if(text!=null) node.textContent=text;
    if(className) node.className=className;
    return node;
  };
  const field=id=>document.getElementById('pm-'+id);
  const query=new URLSearchParams(location.search);
  const bank=field('bank'), instrument=field('instrument'), mode=field('mode'), exclusion=field('exclusion');
  bank.value=query.get('bank')==='ecb'?'ecb':'fed';
  field('dimension').value=query.get('dimension')==='cycle'?'cycle':'leader';
  const digits=n=>Number.isFinite(n)?new Intl.NumberFormat('en-GB',{minimumFractionDigits:2,maximumFractionDigits:2}).format(n).replace('-','−'):'—';
  const numeric=n=>Number.isFinite(n)?n.toLocaleString('en-GB'):'—';
  const ci=values=>Array.isArray(values)&&values.length===2&&values.every(Number.isFinite)?digits(values[0])+' to '+digits(values[1]):'—';
  const proportion=(part,total)=>Number.isFinite(part)&&total>0?part+' / '+total+' ('+(100*part/total).toFixed(0)+'%)':'—';
  const small=text=>el('p',text,'ce-small');
  const disclosure=(title,items)=>{
    const details=el('details');
    details.append(el('summary',title),...items);
    return details;
  };
  function table(title,headers,rows) {
    const outer=el('div',null,'ce-tables');outer.tabIndex=0;outer.setAttribute('role','region');outer.setAttribute('aria-label',title);
    const t=el('table'),head=el('thead'),tr=el('tr'),body=el('tbody');
    for(const name of headers){const th=el('th',name);th.scope='col';tr.append(th);}
    head.append(tr);
    for(const [key,...values] of rows){
      const r=el('tr'),th=el('th',key);th.scope='row';r.append(th);
      for(const v of values) r.append(el('td',v));
      body.append(r);
    }
    t.append(el('caption',title),head,body);outer.append(t);return outer;
  }
  function setOptions(control,options,value){
    control.replaceChildren(...options.map(([key,label])=>new Option(label,key)));
    control.disabled=!options.length;
    control.value=options.some(([v])=>v===value)?value:options[0]?.[0]||'';
  }
  let marketData=null, headlineData=null, speechData=null, stageData=null, currentData=null, anticipatedData=null, regimeData=null, anticipatedHeadlines=null;
  const pointFiles=new Map();
  function eventFile(id){
    if(!pointFiles.has(id)){
      pointFiles.set(id,load(id+'-cross-asset-events').catch(error=>{pointFiles.delete(id);throw error;}));
    }
    return pointFiles.get(id);
  }
  let plotToken=0;
  const svgNs='http://www.w3.org/2000/svg';
  function svg(tag,attrs,text){
    const n=document.createElementNS(svgNs,tag);
    for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));
    if(text!=null)n.textContent=text;
    return n;
  }
  function signed(value){
    return (value>0?'+':'')+digits(value);
  }
  async function renderScatter(){
    const ticket=++plotToken, chosenBank=bank.value, key=instrument.value, predictor=marketData?.banks?.[chosenBank]?.predictors[key];
    const figure=field('scatter'), plot=field('plot'), info=field('point-info'), select=field('asset'), dates=field('plot-date');
    figure.hidden=!predictor;plot.replaceChildren();info.replaceChildren();field('date-control').hidden=true;
    if(!predictor)return;
    setOptions(select,Object.entries(predictor.outcomes).map(([id,v])=>[id,v.label]),select.value||'yield2y');
    const asset=select.value,outcome=predictor.outcomes[asset];
    plot.append(small('Loading individual decision windows…'));

    let file;
    try{file=await eventFile(chosenBank);}catch{if(ticket===plotToken)plot.replaceChildren(small('Individual observations are unavailable. The table above contains the saved estimates.'));return;}
    if(ticket!==plotToken || !window.document || !figure.isConnected)return;
    const {start,end}=marketData.period;
    const points=file.records.filter(r=>r.stage==='release'&&r.type==='decision'&&r.groupEligible&&start<=r.date&&r.date<=end&&Number.isFinite(r.values[key])&&Number.isFinite(r.values[asset]))
      .map(r=>({r,x:r.values[key],y:r.values[asset]})).sort((a,b)=>a.r.date.localeCompare(b.r.date));
    if(!points.length||points.length!==outcome.n){plot.replaceChildren(small('The available point sample does not match the saved regression. Use the table and meeting download for this release.'));return;}
    const xName=predictor.label,yName=outcome.label,yUnit=outcome.unit;
    const left=61,right=590,top=13,bottom=262;
    const tickRange=values=>{
      const min=Math.min(0,...values),max=Math.max(0,...values),raw=(max-min||1)/4;
      const magnitude=10**Math.floor(Math.log10(raw));
      const step=[1,2,2.5,5,10].find(v=>v*magnitude>=raw)*magnitude;
      const low=Math.floor(min/step)*step,high=Math.ceil(max/step)*step;
      return {low,high:high===low?low+step:high,step};
    };
    const xr=tickRange(points.map(p=>p.x)),yr=tickRange(points.map(p=>p.y));
    const X=x=>left+(x-xr.low)/(xr.high-xr.low)*(right-left),Y=y=>bottom-(y-yr.low)/(yr.high-yr.low)*(bottom-top);
    const chart=svg('svg',{class:'pm-scatterplot',viewBox:'0 0 605 295',role:'group','aria-label':yName+' against '+xName+', '+points.length+' meetings'});
    const clipId='pm-plot-area', defs=svg('defs',{}),clip=svg('clipPath',{id:clipId});
    clip.append(svg('rect',{x:left,y:top,width:right-left,height:bottom-top}));defs.append(clip);chart.append(defs);
    const nice=v=>new Intl.NumberFormat('en-GB',{maximumFractionDigits:3,signDisplay:'exceptZero'}).format(v);
    for(let i=0,x=xr.low;x<=xr.high+xr.step/100;i++,x=xr.low+i*xr.step){
      chart.append(svg('line',{x1:X(x),x2:X(x),y1:top,y2:bottom,class:Math.abs(x)<1e-9?'pm-zero':'pm-grid'}),svg('text',{x:X(x),y:bottom+21,'text-anchor':'middle'},nice(x)));
    }
    for(let i=0,y=yr.low;y<=yr.high+yr.step/100;i++,y=yr.low+i*yr.step){
      chart.append(svg('line',{x1:left,x2:right,y1:Y(y),y2:Y(y),class:Math.abs(y)<1e-9?'pm-zero':'pm-grid'}),svg('text',{x:left-7,y:Y(y)+4,'text-anchor':'end'},nice(y)));
    }
    const n=points.length,xMean=points.reduce((a,p)=>a+p.x,0)/n,yMean=points.reduce((a,p)=>a+p.y,0)/n;
    const slope=outcome.slopePer10Bp==null?null:outcome.slopePer10Bp/10;
    if(Number.isFinite(slope)){
      const y=x=>yMean+slope*(x-xMean),min=Math.min(...points.map(p=>p.x)),max=Math.max(...points.map(p=>p.x));
      chart.append(svg('line',{class:'pm-fit',x1:X(min),x2:X(max),y1:Y(y(min)),y2:Y(y(max)),'clip-path':'url(#'+clipId+')'}));
    }
    const anchors=[];let activeIndex=-1;
    function show(i){
      const last=anchors[activeIndex];if(last){last.classList.remove('pm-picked');last.setAttribute('tabindex','-1');}
      activeIndex=i;dates.selectedIndex=i;
      const p=points[i],a=anchors[i],read=el('a','Open the '+p.r.date+' event window');
      a.classList.add('pm-picked');a.setAttribute('tabindex','0');read.href=a.getAttribute('href');
      info.replaceChildren(document.createTextNode(xName+' '+signed(p.x)+' bp · '+yName+' '+signed(p.y)+' '+yUnit+' · '),read);
    }
    setOptions(dates,points.map(p=>[p.r.id,p.r.date]),points[n-1].r.id);
    points.forEach((p,i)=>{
      const href='cross-asset-events.html?'+new URLSearchParams({bank:chosenBank,stage:'release',date:p.r.date,event:p.r.id});
      const title=p.r.date+' · '+xName+' '+signed(p.x)+' bp · '+yName+' '+signed(p.y)+' '+yUnit;
      const a=svg('a',{href,tabindex:-1,class:'pm-plot-link','aria-label':title});a.append(svg('title',{},title),svg('circle',{class:'pm-dot',cx:X(p.x),cy:Y(p.y),r:3.7}));
      a.addEventListener('focus',()=>show(i));a.addEventListener('pointerenter',()=>show(i));
      a.addEventListener('keydown',e=>{
        if(e.key!=='ArrowLeft'&&e.key!=='ArrowRight')return;
        e.preventDefault();const j=Math.max(0,Math.min(n-1,i+(e.key==='ArrowRight'?1:-1)));anchors[j].focus();
      });
      anchors.push(a);chart.append(a);
    });
    plot.replaceChildren(small('Vertical axis: '+yName+' ('+yUnit+'). Horizontal axis: '+xName+' (bp). '+n+' decision windows. The rust line is the fitted regression.'),chart);
    field('date-control').hidden=false;dates.onchange=()=>show(dates.selectedIndex);show(n-1);
  }
  function renderMarket(){
    const box=field('market-output');box.replaceChildren();
    const b=marketData?.banks?.[bank.value];
    const predictors=Object.entries(b?.predictors||{});
    setOptions(instrument,predictors.map(([id,row])=>[id,row.label]),instrument.value);
    renderScatter();
    if(!predictors.length){box.append(small('Market estimates are unavailable for this bank.'));return;}
    const p=b.predictors[instrument.value];
    box.append(small([b.window,p.firstDate&&p.lastDate?p.firstDate+' to '+p.lastDate:'',numeric(p.observedMeetings)+' meetings with this instrument'].filter(Boolean).join(' · ')));
    if(p.description) box.append(small(p.description));
    const outcomes=Object.values(p.outcomes||{});
    const unit=o=>o.unit==='%'?'pp':o.unit;
    const headers=['Asset measure','Unit','Change per +10 bp','95% interval','Meetings','R²'];
    const row=(o,fit)=>[o.label,unit(o),digits(fit?.slopePer10Bp),ci(fit?.ci95),numeric(fit?.n),digits(fit?.rSquared)];
    box.append(table('Observed co-movement in the release window',headers,outcomes.map(o=>row(o,o))));
    box.append(small('For equities and exchange rates, pp denotes percentage points of return. Each row uses meetings with both measures observed. The confidence intervals use heteroskedasticity-robust standard errors.'));
    const sens=outcomes.filter(o=>o.sensitivity);
    if(sens.length){
      const cutoff=sens[0].sensitivity.maxAbsPredictorBp;
      box.append(disclosure('Sensitivity to large rate moves',[
        small('This estimate excludes instrument moves above the 95th percentile in absolute size. The cutoff for this instrument is '+digits(cutoff)+' bp.'),
        table('Release-window estimates with the largest instrument moves excluded',headers,sens.map(o=>row(o,o.sensitivity)))
      ]));
    }
    const covered=outcomes.filter(o=>o.reportCoverage);
    if(covered.length) {
      const rows=covered.flatMap(o=>[['With reports',o.reportCoverage.covered],['Without reports',o.reportCoverage.withoutReport]].map(([group,fit])=>[o.label+' · '+group,...row(o,fit).slice(1)]));
      box.append(disclosure('Meetings with and without verified reports',[
        small('Separate regressions use the events in each group. Coverage differences can reflect which meetings were reported or recovered.'),
        table('Sensitivity by availability of reports',headers,rows)
      ]));
    }
    const common=outcomes.filter(o=>o.commonCalendar);
    if(common.length) box.append(disclosure('Same calendar period for both banks',[
      table('January 2004 to December 2025',headers,common.map(o=>row(o,o.commonCalendar)))
    ]));
    const source=el('a',b.sourceLabel||'Market data source');
    if(b.sourceUrl) source.href=b.sourceUrl;
    const descriptions=(marketData.methods||[]).map(small);if(b.sourceUrl) descriptions.push(source);
    if(descriptions.length) box.append(disclosure('Observations and estimation',descriptions));
  }
  const reutersPanel=field('reuters-2025');
  let reutersRequest;
  reutersPanel.addEventListener('toggle',async()=>{
    if(!reutersPanel.open||reutersRequest)return;
    const output=field('reuters-output');
    output.replaceChildren(small('Loading 2025 meetings…'));
    try{
      reutersRequest=load('reuters-fomc-2025');
      const rows=await reutersRequest;
      const matched=rows.filter(r=>Number.isFinite(r.ois1yBp)&&Number.isFinite(r.conferenceOis1yBp)&&r.ois1yBp!==0&&r.conferenceOis1yBp!==0);
      const reversed=matched.filter(r=>Math.sign(r.ois1yBp)!==Math.sign(r.conferenceOis1yBp)).length;
      const bothMaterial=matched.filter(r=>Math.abs(r.ois1yBp)>1&&Math.abs(r.conferenceOis1yBp)>1);
      const materialOpposed=bothMaterial.filter(r=>Math.sign(r.ois1yBp)!==Math.sign(r.conferenceOis1yBp)).length;
      const grid=table('Reuters reports and one-year OIS by communication window (bp)',
        ['Meeting','Reuters headline emphasis','Decision gap','OIS at statement','OIS at conference'],
        rows.map(r=>[r.date,r.titleReading,signedOrMissing(r.pricingGapBp),signedOrMissing(r.ois1yBp),signedOrMissing(r.conferenceOis1yBp)]));
      grid.querySelectorAll('tbody tr').forEach((tr,i)=>{
        const r=rows[i];
        if(!r.articleUrl)return;
        const link=el('a',r.date);
        link.href=r.articleUrl;
        link.setAttribute('aria-label','Reuters report for '+r.date);
        tr.querySelector('th').replaceChildren(link);
      });
      output.replaceChildren(small('The statement and press-conference OIS changes had opposite signs on '+reversed+' of '+matched.length+' dates. When both moves exceeded 1 bp in size, '+materialOpposed+' of '+bothMaterial.length+' moved in opposite directions. A closing headline can therefore describe a different part of the meeting from the initial price move.'),grid,
        small('The CSV gives the headline reading, the original story link, available timing evidence and both market windows. The July reading comes from an indexed Reuters edition. This separate eight-meeting sample uses the official calendar as its denominator. The historical four-publisher comparison retains its original corpus.'));
    }catch{
      reutersRequest=null;
      output.replaceChildren(small('The table is unavailable. Download the meeting CSV below.'));
    }
  });
  if(location.hash==='#pm-reuters-2025')reutersPanel.open=true;
  function renderAnticipatedNews(){
    const box=field('anticipated-news');box.replaceChildren();
    const result=anticipatedHeadlines?.banks?.find(r=>r.bank===bank.value);
    if(!result)return;
    const period=anticipatedHeadlines.period;
    const variants=[['Anticipated · confirmed post-release',result.anticipated],['All decisions · confirmed post-release',result.allEligible],['Anticipated · confirmed, excluding WSJ',result.withoutWSJ],['Anticipated · all report editions',result.retrospective]];
    if(bank.value==='ecb' && result.reportedStep)variants.push(['Rounded step narratives · separate context',result.reportedStep]);
    const rows=variants.map(([name,s])=>[name,numeric(s.nDecisions),numeric(s.nDecisions-s.nWithReport),
      s.nDirectional+' / '+s.nDecisions,numeric(s.nDirectionalWithOis),numeric(s.nMaterialDirectional),
      s.nMaterialDirectional?proportion(s.nAligned,s.nMaterialDirectional):'0 / 0 (—)']);
    const note=small(period.start+' to '+period.end+'. This comparison always uses decision gaps within 5 bp and absolute one-year OIS changes above 1 bp. It uses reports, with its own timing and publisher rules.');
    const stats=table('Headline direction and the decision-release OIS move',['Sample','Decisions','No qualifying report','Directional / decisions','Directional with OIS','Directional with |OIS| >1 bp','Aligned / material'],rows);
    const timing=small('The primary screen requires the first publication clock to follow the release, or a later edition date whose earliest possible publication follows it. The reviewed title may reflect later changes. Including all report editions also admits unresolved timing and stories posted at or before release.');
    const bySource=result.sourceCoverage.map(s=>s.publisher+' '+s.anticipatedMeetings).join(' · ');
    const filter=small('Anticipated meetings with an eligible report by outlet · '+bySource+'. Multiple outlets can cover one meeting. The archive spans four publishers and has uneven coverage across years.');
    const examples=el('div');
    const events=anticipatedHeadlines.events.filter(e=>e.bank===bank.value&&e.anticipated&&Number.isFinite(e.ois1yBp)&&Math.abs(e.ois1yBp)>1).sort((a,b)=>a.date.localeCompare(b.date));
    const direction=d=>d==='tighter'||d==='easier';
    for(const [label,kind,records] of [
      ['Confirmed after release','postRelease',events.filter(e=>direction(e.postRelease.direction))],
      ['Direction appears only in the broader reading','retrospective',events.filter(e=>direction(e.retrospective.direction)&&!direction(e.postRelease.direction))]
    ]){
      for(const e of records){
        const read=e[kind];
        const report=e.reports.find(r=>r.path===read.direction && read.ballots[r.publisher]===read.direction &&
          (kind==='postRelease'?r.chronology.startsWith('post-release'):!r.chronology.startsWith('post-release')));
        if(!report)continue;
        const p=small(label+' · '+e.date+' decision · '+read.direction+' path · one-year OIS '+signed(e.ois1yBp)+' bp. ');
        const a=el('a',report.publisher+' · '+(report.publishedAt||report.publicationDate));a.href=report.url;p.append(a);examples.append(p);break;
      }
    }
    const download=el('a','Download the event votes, publication evidence and source URLs (JSON)');download.href='data/anticipated-headlines.json';download.download='';
    box.append(disclosure('Did coverage agree with the path when the decision was anticipated?',[note,stats,timing,filter,examples,download]));
  }
  function renderNews(){
    const box=field('news-output');box.replaceChildren();
    const b=headlineData?.banks?.find(row=>row.bank===bank.value);
    const variants=(b?.variants||[]).filter(v=>v.mode===mode.value);
    setOptions(exclusion,variants.map(v=>[v.exclusion||'',v.exclusion?'Exclude '+v.exclusion:'All four publishers']),exclusion.value);
    if(!variants.length){box.append(small('Headline comparisons are unavailable for this bank and coverage type.'));return;}
    const v=variants.find(s=>(s.exclusion||'')===exclusion.value);
    box.append(small([headlineData.start&&headlineData.end?headlineData.start+' to '+headlineData.end:'',b.instrument,b.window,numeric(v.nEvents)+' meetings with coverage',numeric(v.nPriced)+' with rate observations'].filter(Boolean).join(' · ')));
    const labels={tighter:'Tighter policy',easier:'Easier policy',noDirectionalSignal:'No explicit direction',split:'Split directions'};
    const rows=v.groups.map(g=>[labels[g.direction]||g.direction,numeric(g.nEvents),numeric(g.nPriced),digits(g.medianBp),
      ['tighter','easier'].includes(g.direction)?proportion(g.alignedN,g.materialN):'—']);
    box.append(table('Signed rate changes by headline direction',['Policy path in coverage','Meetings','With rate data','Median move (bp)','Same direction among moves >1 bp in size'],rows));
    if(mode.value==='report') box.append(small('A report may incorporate a later press conference or edits made after the decision window.'));
    else box.append(small('A preview describes the meeting in advance. The wording reviewed here can come from a later version of the page.'));
    box.append(small('Positive rate changes indicate higher pricing. Alignment counts tighter headlines with a positive move and easier headlines with a negative move. It uses moves larger than 1 bp in absolute size. A dash marks an unavailable or inapplicable comparison.'));
    const overlap=b.overlap||[];
    if(overlap.length && mode.value==='report' && !exclusion.value) {
      box.append(disclosure('How often do publishers agree?',[
        small('Each pair is compared on decisions covered by both outlets. The agreement rate uses meetings where both supplied a directional reading.'),
        table('Report coverage shared by each pair',['Publishers','Shared decisions','Both directional','Same direction'],overlap.map(r=>[r.publisherA+' and '+r.publisherB,numeric(r.nShared),numeric(r.nBothDirectional),proportion(r.nSameDirection,r.nBothDirectional)]))
      ]));
    }
    if(mode.value==='report' && !exclusion.value && b.basisChecks?.length) {
      const checks=b.basisChecks.flatMap(v=>v.groups.filter(g=>g.direction==='tighter'||g.direction==='easier').map(g=>[
        (v.basis==='level'?'Future policy level':'Revision to the earlier path')+' · '+labels[g.direction],numeric(g.nEvents),numeric(g.nPriced),digits(g.medianBp),proportion(g.alignedN,g.materialN)]));
      box.append(disclosure('Future policy level or a change in the expected path?',[
        table('Titles with an explicit direction and policy-path basis',['Policy-path comparison','Meetings','With rate data','Median move (bp)','Material moves aligned'],checks)
      ]));
    }
    if(headlineData.method?.length) box.append(disclosure('Headline coding and sample',headlineData.method.map(small)));
  }
  function renderStages(){
    const box=field('stage-output');box.replaceChildren();
    const s=stageData?.banks?.[bank.value];if(!s?.groups?.length)return;
    const rows=s.groups.map(g=>[g.label,numeric(g.n),g.n>=10?digits(g.releaseMedianAbsBp):'—',g.n>=10?digits(g.conferenceMedianAbsBp):'—',g.n>=10?proportion(g.conferenceLarger,g.n):'—',numeric(g.ties)]);
    const download=el('a','Download meeting stage comparisons (JSON)');download.href='data/meeting-stage-study.json';download.download='';
    box.append(disclosure('When did the policy path reprice?',[
      small('Each meeting has both a decision-release window and a press-conference window. Medians use the absolute one-year OIS change. Groups with fewer than ten meetings show counts only.'),
      table('Paired one-year OIS changes',['Meeting sample','Meetings','Release median (bp)','Conference median (bp)','Larger move at conference','Ties'],rows),
      ...[s.note,...(stageData.method||[])].filter(v=>typeof v==='string').map(small),download
    ]));
  }
  function renderSpeech(){
    const box=field('speech-output');box.replaceChildren();
    const panels=(speechData?.panels||[]).filter(p=>p.bank===bank.value);
    if(!panels.length){box.append(small('Speech comparisons are unavailable for this bank.'));return;}
    for(const p of panels){
      box.append(el('h3',p.label));
      for(const text of [p.description,p.coverage]) if(text) box.append(small(text));
      const toneTable=(groups,title)=>{
        const names=[...new Set(groups.flatMap(g=>g.readings.map(r=>r.name)))];
        const stats=names.map(name=>[name,...groups.map(g=>{
          const r=g.readings.find(x=>x.name===name);
          if(!r||!Number.isFinite(r.median))return '—';
          return digits(r.median)+' '+r.unit+' ['+digits(r.q1)+', '+digits(r.q3)+'] · n = '+r.n;
        })]);
        return table(title,['Measure',...groups.map(g=>g.label)],stats);
      };
      box.append(toneTable(p.groups,'Median change [25th, 75th percentiles] and usable observations by tone'));
      if(p.bank==='ecb' && p.notes?.length)box.append(small(p.notes[p.notes.length-1]));
      if(p.oneDaySensitivity?.length)box.append(disclosure('Consecutive calendar days only',[
        small('This check excludes pairs of fixings separated by weekends or holidays.'),toneTable(p.oneDaySensitivity,'Daily changes over a single calendar day')
      ]));
      for(const [leader,groups] of Object.entries(p.withinLeader||{}))box.append(disclosure('Within the '+leader+' sample',[
        toneTable(groups,'Speech tone and yield changes during one chair’s tenure')
      ]));
      if(p.strata?.length)box.append(disclosure('Composition of the speech sample',[
        table('Scored speeches by subgroup',['Group','Speeches','Hawkish','Dovish','Neutral'],p.strata.map(v=>[v.label,numeric(v.n),numeric(v.hawkish),numeric(v.dovish),numeric(v.neutral)]))
      ]));
      if(p.notes?.length) box.append(disclosure('Speech sample and measurement',(p.bank==='ecb'?p.notes.slice(0,-1):p.notes).map(small)));
    }
    if(bank.value==='fed' && speechData.example) {
      const example=speechData.example,links=el('div',null,'ce-links');
      for(const [label,url] of [['Official speech',example.url],['Market observations',example.marketSource]]) {
        if(url){const a=el('a',label);a.href=url;links.append(a);}
      }
      box.append(el('h3',example.title),small(example.description),links);
    }
    const sourceLinks=(speechData.sources||[]).map(s=>{const a=el('a',s.label);a.href=s.url;return a;});
    const sources=el('div',null,'ce-links');sources.append(...sourceLinks);
    box.append(disclosure('Speech methods and data sources',[...(speechData.methods||[]).map(small),sources]));
  }
  const curvePanel=field('curve-composition');
  // Site quotes are in basis points. Round the difference at the precision of the source series.
  const slopeChange=r=>Number((r.values.yield10y-r.values.yield2y).toFixed(7));
  const curveBand=field('curve-band');
  if(['1','2','5'].includes(query.get('curveBand')))curveBand.value=query.get('curveBand');
  curveBand.onchange=()=>{
    const url=new URL(location.href);
    url.searchParams.set('curveBand',curveBand.value);
    history.replaceState(null,'',url);
    renderCurve();
  };
  function curveForecast(rows,band){
    const period=(start,end)=>rows.filter(r=>r.date.slice(0,4)>=start && r.date.slice(0,4)<=end);
    const flattened=r=>Number(slopeChange(r)<-band);
    const count=sample=>sample.reduce((sum,r)=>sum+flattened(r),0);
    const test=period('2018','2025'), train=[period('2000','2008'),period('2009','2017')];
    if(!test.length || train.some(sample=>!sample.length))return small('A training or test period has no matched decision windows.');
    const probabilities=train.map(sample=>count(sample)/sample.length);
    const loss=(probability,sample)=>sample.reduce((sum,r)=>sum+(probability-flattened(r))**2,0)/sample.length;
    const scores=train.map((sample,i)=>[i?'2009–2017':'2000–2008',proportion(count(sample),sample.length),
      loss(probabilities[i],test).toFixed(4)]);
    const items=[small('Before each test meeting, each benchmark assigns the fraction of its training releases that flattened by more than '+band+' bp. Both are scored on the same 2018–2025 releases. The observed test frequency was '+proportion(count(test),test.length)+'.'),
      table('Forecast of flattening by more than '+band+' bp · release windows',['Training years','Flattened / matched training releases','Test Brier score'],scores),
      small('The Brier score averages the squared difference between the forecast probability and the outcome (one for flattening, zero otherwise). Lower scores indicate more accurate probabilities. These fixed frequencies use the available historical data vintage and ignore information about the individual meeting.')];
    const differences=[];
    for(const year of new Set(test.map(r=>r.date.slice(0,4)))){
      const remaining=test.filter(r=>!r.date.startsWith(year));
      if(remaining.length)differences.push(loss(probabilities[0],remaining)-loss(probabilities[1],remaining));
    }
    if(differences.length)items.push(small('Dropping one test year at a time gives an early-minus-later score difference from '+Math.min(...differences).toFixed(4)+' to '+Math.max(...differences).toFixed(4)+'. Negative values favour the earlier period. This range measures sensitivity to the years included.'));
    if(count(test)<5)items.push(small('Only '+count(test)+' test releases crossed this threshold. A small Brier score is common for a rare event. Compare training periods at the same threshold.'));
    items.push(small('A forecast of zero probability at every meeting scores '+loss(0,test).toFixed(4)+' on this same test sample. The frequency estimates are descriptive and omit trading costs.'));
    const forecast=disclosure('Did the 2000–2008 flattening frequency forecast later releases better?',items);
    forecast.open=new URLSearchParams(location.search).has('curveBand');
    return forecast;
  }
  async function renderCurve(){
    if(!curvePanel.open)return;
    const id=bank.value,box=field('curve-output');
    box.replaceChildren(small('Loading matched yield changes…'));
    let file;
    try{file=await eventFile(id);}catch{
      if(bank.value===id)box.replaceChildren(small('The event observations are unavailable.'));
      return;
    }
    if(bank.value!==id || !curvePanel.open)return;
    const output=[],band=Number(curveBand.value);
    for(const stage of ['release','conference']){
      const eligible=file.records.filter(r=>r.groupEligible && r.stage===stage);
      const paired=eligible.filter(r=>Number.isFinite(r.values.yield2y) && Number.isFinite(r.values.yield10y)).sort((a,b)=>a.date.localeCompare(b.date));
      if(!paired.length)continue;
      const label=stage==='release'?'Decision release':'Press conference';
      const above=paired.filter(r=>slopeChange(r)>band),below=paired.filter(r=>slopeChange(r)<-band);
      const groups=[['Steepened >'+band+' bp',above],['Flattened >'+band+' bp',below]].map(([name,group])=>{
        const legs=group.map(r=>[r.values.yield2y,r.values.yield10y]);
        return [name,group.length,legs.filter(([a,b])=>a>0 && b>0).length,legs.filter(([a,b])=>a<0 && b<0).length,
          legs.filter(([a,b])=>a*b<0).length,legs.filter(([a,b])=>a===0 || b===0).length];
      });
      output.push(table(label+' · '+paired[0].date+' to '+paired.at(-1).date,['Curve move','Events','Both yields rose','Both fell','Opposite signs','One unchanged'],groups),
        small(paired.length+' of '+eligible.length+' eligible windows have both yields. In '+(paired.length-above.length-below.length)+' the change in slope was within ±'+band+' bp, including the boundaries.'));
      if(stage==='release'){
        const example=below.filter(r=>r.values.yield2y*r.values.yield10y<0).at(-1);
        if(example){
          const note=small('On '+example.date+' the two-year yield rose '+digits(example.values.yield2y)+' bp and the ten-year fell '+digits(-example.values.yield10y)+' bp. The change in slope was '+signed(example.values.yield10y)+' − ('+signed(example.values.yield2y)+') = '+signed(slopeChange(example))+' bp. Window: '+example.window+'. ');
          const link=el('a','Inspect this decision');link.href='cross-asset-events.html?'+new URLSearchParams({bank:id,stage,date:example.date,event:example.id});note.append(link);output.push(note);
        }
        output.push(curveForecast(paired,band));
      }
    }
    const link=el('a',id==='fed'?'San Francisco Fed event workbook':'ECB event workbook');
    link.href=id==='fed'?'https://www.frbsf.org/wp-content/uploads/USMPD.xlsx':'https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx';
    box.replaceChildren(...output,link);
  }
  curvePanel.addEventListener('toggle',renderCurve);
  if(location.hash==='#pm-curve-composition')curvePanel.open=true;
  const projectionPanel=field('fed-projections');

  async function showProjectionComparison(){
    if(!projectionPanel.open) return;
    const box=field('projections-output');
    box.replaceChildren(small('Loading Fed announcement windows…'));
    try {
      const data=await eventFile('fed');
      const releases=data.records.filter(r=>r.stage==='release' && r.scheduled===true && r.date>='2019-01-01' && typeof r.sep==='boolean');
      const dates=releases.map(r=>r.date).sort();
      const inside=x=>Math.abs(x)<=1.0000001;
      const results=[true,false].map(sep=>{
        const group=releases.filter(r=>r.sep===sep);
        const matched=group.filter(r=>Number.isFinite(r.values.currentMeeting) && Number.isFinite(r.values.nextMeeting));
        const anticipated=matched.filter(r=>inside(r.values.currentMeeting));
        const moves=anticipated.map(r=>r.values.nextMeeting);
        return [sep?'With projections':'Without projections',proportion(matched.length,group.length),numeric(anticipated.length),
          numeric(moves.filter(x=>x>1.0000001).length),numeric(moves.filter(x=>x< -1.0000001).length),proportion(moves.filter(x=>!inside(x)).length,moves.length)];
      });
      box.replaceChildren(table('Scheduled statements · '+(dates[0]||'—')+' to '+(dates.at(-1)||'—'),
        ['Meeting','Both prices / scheduled','MP1 within ±1 bp','MP2 up >1 bp¹','MP2 down >1 bp¹','MP2 outside band¹'],results),
        small('¹ Among meetings where the current decision was within ±1 bp of prior pricing. Each count measures the statement window only.'));
    } catch {
      box.replaceChildren(small('The Fed statement observations are unavailable.'));
    }
  }
  projectionPanel.addEventListener('toggle',showProjectionComparison);
  if(location.hash==='#pm-fed-projections') projectionPanel.open=true;
  function renderAnticipated(){
    const box=field('anticipated-output'),threshold=field('threshold');
    field('ecb-case').hidden=bank.value!=='ecb';
    projectionPanel.hidden=bank.value!=='fed';
    box.replaceChildren();
    const b=anticipatedData?.banks?.[bank.value],sets=b?.thresholds||[];
    setOptions(threshold,sets.map(s=>[String(s.thresholdBp),s.thresholdBp+' bp']),threshold.value||String(anticipatedData?.defaultThresholdBp??5));
    const selected=sets.find(s=>String(s.thresholdBp)===threshold.value);
    if(!selected){box.append(small('Decision and path estimates are unavailable for this bank.'));return;}
    const order=[['anticipated','Within '+threshold.value+' bp'],['surprise','Beyond '+threshold.value+' bp']];
    if(bank.value==='ecb' && selected.groups.reportedStep)order.push(['reportedStep','Rounded step narrative · contextual']);
    order.push(['unpriced','No comparable prior']);
    const rows=order.map(([id,label])=>{
      const g=selected.groups[id],m=g.metrics.ois1yBp,p=g.pathMove;
      return [label,numeric(g.n),numeric(m.n),digits(m.medianAbs),proportion(p.over1Bp,p.n),proportion(p.over5Bp,p.n)];
    });
    const coverage=b.coverage||{};
    if(Number.isInteger(coverage.comparableGaps))box.append(small(numeric(coverage.comparableGaps)+' decision releases have a comparable actual-minus-priced move. One-year OIS spans the current decision and future policy expectations. Its movement can also reflect risk premia.'));
    box.append(table('One-year OIS moves in the decision-release window',[bank.value==='ecb'?'Reported gap at source precision':'Decision gap','Meetings','OIS observations','Median absolute move (bp)','Absolute move >1 bp','Absolute move >5 bp'],rows));
    if(bank.value==='ecb' && Number.isInteger(coverage.comparableGaps)){
      const text=Number.isInteger(coverage.rawComparableGaps)?numeric(coverage.rawComparableGaps)+' releases have source-reported pricing for the deposit rate. '+numeric(coverage.comparableGaps)+' have a numeric curve increment eligible for a threshold comparison.':'Only '+numeric(coverage.comparableGaps)+' ECB releases have comparable prior pricing.';
      box.append(small(text+' Rounded step descriptions cannot resolve smaller tolerances. The beyond-threshold OIS sample has '+numeric(selected.groups.surprise.pathMove.n)+' '+(selected.groups.surprise.pathMove.n===1?'meeting':'meetings')+'. These groups are too small for statistical comparisons.'));
      if(b.priorAudit?.length){
        const evidence=b.priorAudit.map(r=>[r.date,r.priorEvidenceType==='reportedCurveIncrement'?'Numeric curve increment':'Rounded step narrative',digits(r.priorMoveBp),digits(r.comparisonGapBp),r.sourceAudit||'—']);
        const auditTable=table('ECB deposit-rate pricing evidence by decision date',['Meeting date','Source evidence','Reported move (bp)','Gap used for thresholds (bp)','Evidence and source'],evidence);
        [...auditTable.querySelectorAll('tbody tr')].forEach((tr,i)=>{
          const r=b.priorAudit[i];if(!r.pricingSource)return;
          const read=el('a',' Read source');read.href=r.pricingSource;tr.lastElementChild.append(read);
        });
        const auditNotes=[auditTable],rounded=b.reportedStepSensitivity;
        if(rounded?.anticipated && rounded.surprise)auditNotes.push(small('Treating the rounded step descriptions as point quotes gives '+numeric(rounded.anticipated.n)+' decisions within '+rounded.thresholdBp+' bp and '+numeric(rounded.surprise.n)+' beyond it. This sensitivity depends on the rounding assumption.'));
        box.append(disclosure('Inspect each ECB prior and its source',auditNotes));
      }
    }
    const curves=order.flatMap(([id,label])=>{
      const curve=selected.groups[id].pairedCurve;
      if(!curve)return [];
      return [['OIS up >1 bp',curve.oisUpOver1Bp],['OIS down >1 bp',curve.oisDownOver1Bp]].filter(([,sample])=>sample).map(([direction,sample])=>[
        label+' · '+direction,numeric(sample.n),proportion(sample.steeper,sample.n),proportion(sample.flatter,sample.n),numeric(sample.unchanged)
      ]);
    });
    if(curves.length) box.append(disclosure('How often did the 2s10s curve steepen or flatten?',[
      table('Joint one-year OIS and 10Y less 2Y yield changes',['Decision gap and OIS direction','Paired meetings','Steepened','Flattened','Unchanged'],curves)
    ]));
    const changes=order.flatMap(([id,label])=>{
      const g=selected.groups[id];
      return [['yield2yBp','2Y yield (bp)'],['slope2s10sBp','10Y less 2Y (bp)'],['equityPct','Equity return (%)']].map(([key,name])=>{
        const m=g.metrics[key];return [label+' · '+name,numeric(m.n),digits(m.median),digits(m.q25),digits(m.q75)];
      });
    });
    box.append(disclosure('Yields, the curve and equities',[
      table('Signed change by decision gap',['Sample and measure','Meetings with quotes','Median','25th percentile','75th percentile'],changes)
    ]));
    const examples=bank.value==='fed'?anticipatedData.fedResidual?.examples:null;
    if(examples?.length){
      const hold=examples.find(e=>e.date==='2004-01-28' && e.actionBp===0 && e.pricingGapBp===0);
      if(hold){
        const note=small('On 28 January 2004 the Fed delivered a fully priced hold. One-year OIS rose '+digits(hold.ois1yBp)+' bp and the two-year Treasury yield rose '+digits(hold.yield2yBp)+' bp. ');
        const event=el('a','Inspect this meeting');event.href='cross-asset-events.html?'+new URLSearchParams({bank:'fed',stage:'release',date:hold.date,event:'fed-'+hold.date+'-release'});
        note.append(event);box.append(note);
      }
      const list=el('div',null,'ce-links');
      for(const e of examples){const l=el('a',e.date+' · '+signed(e.residualOis1yBp)+' bp');l.href='cross-asset-events.html?'+new URLSearchParams({bank:'fed',stage:'release',date:e.date,event:'fed-'+e.date+'-release'});list.append(l);}
      box.append(disclosure('Fed meetings with large residual path moves',[
        small('The in-sample model uses '+numeric(anticipatedData.fedResidual.n)+' meetings and has an R² of '+digits(anticipatedData.fedResidual.rSquared)+'.'),
        small('Each residual is the observed one-year OIS change minus the change fitted from the current-meeting Fed futures surprise. Other information released at the same time can move the residual.'),list
      ]));
    }
    if(anticipatedData.methods?.length) box.append(disclosure('Pricing gaps and measurement',anticipatedData.methods.map(small)));
  }
  function renderRegimes(){
    const box=field('regimes-output'),asset=field('regime-asset');box.replaceChildren();
    const b=regimeData?.banks?.[bank.value],frame=b?.frames?.[field('frame').value],dim=field('dimension').value;
    const groups=frame?.groups?.[dim]||[],names={yield2y:'2Y sovereign yield',yield10y:'10Y sovereign yield',slope:'10Y less 2Y',equity:'Equity index',eurusd:'EUR/USD'};
    setOptions(asset,Object.entries(names).filter(([key])=>groups.some(g=>g.outcomes?.[key])),asset.value||'yield2y');
    if(!groups.length){box.append(small('Subgroup estimates are unavailable for this bank.'));return;}
    const unit=['equity','eurusd'].includes(asset.value)?'percentage points of return':'bp';
    box.append(small(frame.start+' to '+frame.end+' · '+numeric(frame.predictorMeetings)+' of '+numeric(frame.eligibleMeetings)+' eligible releases have a one-year OIS quote. Coefficients are in '+unit+' per 10 bp of OIS repricing.'));
    if(dim==='cycle' && b.cycleMethod)box.append(small(b.cycleMethod));
    const rows=groups.map(g=>{
      const o=g.outcomes[asset.value];
      return [g.label,numeric(o?.n),digits(o?.slopePer10Bp),ci(o?.ci95),o?.status==='estimated'?digits(o.rSquared):o?.status||'—'];
    });
    box.append(table(names[asset.value]+' sensitivity by '+(dim==='leader'?'tenure':'economic cycle'),[dim==='leader'?'Chair or president':'Cycle phase','Paired observations','Change per +10 bp','95% interval','R² or reason withheld'],rows));
    box.append(small('Estimates require at least 20 observations, five distinct rate changes and rate moves on both sides of zero. Wider intervals indicate less precise estimates.'));
    for(const g of groups) {
      const o=g.outcomes[asset.value];
      if(o?.status==='estimated' && o.tenBpExceedsObservedSpan)box.append(small(g.label+' · A 10 bp comparison exceeds the observed OIS range of '+signed(o.minPredictorBp)+' to '+signed(o.maxPredictorBp)+' bp.'));
    }
    const c=frame.cycleContrast;
    if(dim==='cycle' && c && asset.value==='yield2y'){
      box.append(small('Contraction minus outside-contraction sensitivity for the 2Y yield · '+(Number.isFinite(c.differencePer10Bp)?digits(c.differencePer10Bp)+' bp per 10 bp, 95% interval '+ci(c.ci95)+' bp':'Estimate withheld')+' · '+numeric(c.contractionN)+' contraction and '+numeric(c.outsideN)+' other observations.'));
    }
    const notes=(regimeData.method||[]).map(small);
    for(const [label,url] of [['Release-window source',b.sourceUrl],['Cycle chronology',b.cycleSourceUrl]]){if(url){const a=el('a',label);a.href=url;const p=el('p',null,'ce-small');p.append(a);notes.push(p);}}
    if(notes.length)box.append(disclosure('Subgroup definitions and uncertainty',notes));
  }
  function renderCurrentPricing(rows){
    const output=field('current-pricing');
    output.replaceChildren();
    if(!rows.length)return;
    const fed=bank.value==='fed';
    const entries=rows.map(r=>[r.date,digits(r.actionBp),digits(r.priorMoveBp),digits(r.comparisonGapBp),
      signedOrMissing(r.ois1yBp),signedOrMissing(r.slope2s10sBp)]);
    const notes=fed
      ? 'The Fed prior is inferred from the announced change and the current-meeting futures surprise.'
      : 'The June 2026 account describes a rounded 25 bp step. A reported policy step alone leaves the comparison gap blank.';
    const contents=[small('Official decisions through '+currentData.asOf+'. '+notes),
      table('2026 decision and release-window observations, in basis points',
        ['Meeting','Decision','Prior move at source precision','Comparison gap','One-year OIS','10Y less 2Y'],entries)];
    if(fed){
      const paired=rows.filter(r=>Number.isFinite(r.comparisonGapBp)&&Math.abs(r.comparisonGapBp)<=5&&Number.isFinite(r.ois1yBp));
      const moved=paired.filter(r=>Math.abs(r.ois1yBp)>1).length;
      contents.unshift(small('At a 5 bp decision tolerance, '+moved+' of '+paired.length+' matched 2026 releases moved one-year OIS by more than 1 bp.'));
    }
    contents.push(small('A dash denotes an unavailable estimate. The historical results above use decisions through December 2025.'));
    output.append(disclosure('What happened in 2026?',contents));
  }
  function signedOrMissing(value){return Number.isFinite(value)?signed(value):'—';}
  function render(){
    renderMarket();renderNews();renderSpeech();renderStages();renderAnticipated();renderRegimes();renderAnticipatedNews();
    const current=field('current'),rows=currentData?.records.filter(r=>r.bank===bank.value)||[];
    reutersPanel.hidden=bank.value!=='fed';
    renderCurrentPricing(rows);
    current.hidden=!rows.length;
    if(rows.length){
      const observed=rows.filter(r=>Number.isFinite(r.ois1yBp)&&Number.isFinite(r.yield2yBp)).length;
      const latest=rows.map(r=>r.date).sort().at(-1), lastWindow=currentData.models[bank.value].latestWindowDate;
      current.textContent='2026 update through '+currentData.asOf+' · '+observed+' of '+rows.length+' decisions have both one-year OIS and two-year yield observations ('+(rows.length-observed)+' missing). Latest decision '+latest+'. Latest matched window '+(lastWindow||'unavailable')+'. The regressions above use completed years through 2025.';
    }
    field('events').href='cross-asset-events.html?bank='+bank.value+'&lens=news#ce-news-coverage';
  }
  bank.onchange=()=>{instrument.value='';exclusion.value='';render();renderCurve();const url=new URL(location.href);url.searchParams.set('bank',bank.value);history.replaceState(null,'',url);};
  field('threshold').onchange=renderAnticipated;
  for(const id of ['frame','regime-asset'])field(id).onchange=renderRegimes;
  field('dimension').onchange=()=>{
    const url=new URL(location.href);url.searchParams.set('dimension',field('dimension').value);history.replaceState(null,'',url);renderRegimes();
  };
  field('asset').onchange=renderScatter;
  instrument.onchange=renderMarket; mode.onchange=()=>{exclusion.value='';renderNews();};exclusion.onchange=renderNews;
  async function load(file){
    const r=await fetch('data/'+file+'.json');
    if(!r.ok) throw Error('Unavailable');
    return r.json();
  }
  load('anticipated-headlines').then(data=>{anticipatedHeadlines=data;renderAnticipatedNews();}).catch(()=>{});
  Promise.allSettled([load('anticipated-decisions'),load('policy-regimes')]).then(([anticipated,regimes])=>{
    anticipatedData=anticipated.value;regimeData=regimes.value;renderAnticipated();renderRegimes();
  });
  Promise.allSettled([load('policy-response-study'),load('headline-policy-study'),load('speech-response-study'),load('meeting-stage-study'),load('policy-current-year')]).then(([market,news,speech,stage,current])=>{
    marketData=market.value;headlineData=news.value;speechData=speech.value;stageData=stage.value;currentData=current.value;render();
  });
})();
