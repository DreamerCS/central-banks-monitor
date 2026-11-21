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
  let marketData=null, headlineData=null, speechData=null, stageData=null, currentData=null;
  const pointFiles=new Map();
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
    if(!pointFiles.has(chosenBank))pointFiles.set(chosenBank,load(chosenBank+'-cross-asset-events').catch(e=>{pointFiles.delete(chosenBank);throw e;}));
    let file;
    try{file=await pointFiles.get(chosenBank);}catch{if(ticket===plotToken)plot.replaceChildren(small('Individual observations are unavailable. The table above contains the saved estimates.'));return;}
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
  function render(){
    renderMarket();renderNews();renderSpeech();renderStages();
    const current=field('current'),rows=currentData?.records.filter(r=>r.bank===bank.value)||[];
    current.hidden=!rows.length;
    if(rows.length){
      const observed=rows.filter(r=>Number.isFinite(r.ois1yBp)&&Number.isFinite(r.yield2yBp)).length;
      const latest=rows.map(r=>r.date).sort().at(-1), lastWindow=currentData.models[bank.value].latestWindowDate;
      current.textContent='2026 update through '+currentData.asOf+' · '+observed+' of '+rows.length+' decisions have both one-year OIS and two-year yield observations ('+(rows.length-observed)+' missing). Latest decision '+latest+'. Latest matched window '+(lastWindow||'unavailable')+'. The regressions above use completed years through 2025.';
    }
    field('events').href='cross-asset-events.html?bank='+bank.value+'&lens=news#ce-news-coverage';
  }
  bank.onchange=()=>{instrument.value='';exclusion.value='';render();const url=new URL(location.href);url.searchParams.set('bank',bank.value);history.replaceState(null,'',url);};
  field('asset').onchange=renderScatter;
  instrument.onchange=renderMarket; mode.onchange=()=>{exclusion.value='';renderNews();};exclusion.onchange=renderNews;
  async function load(file){
    const r=await fetch('data/'+file+'.json');
    if(!r.ok) throw Error('Unavailable');
    return r.json();
  }
  Promise.allSettled([load('policy-response-study'),load('headline-policy-study'),load('speech-response-study'),load('meeting-stage-study'),load('policy-current-year')]).then(([market,news,speech,stage,current])=>{
    marketData=market.value;headlineData=news.value;speechData=speech.value;stageData=stage.value;currentData=current.value;render();
  });
})();
