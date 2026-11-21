(() => {
  'use strict';
  const field=id=>document.getElementById('pd-'+id);
  const bank=field('bank'),asset=field('asset'),tolerance=field('threshold'),kind=field('kind'),group=field('group');
  const params=new URL(location.href).searchParams;
  bank.value=params.get('bank')==='ecb'?'ecb':'fed';
  const initial={asset:params.get('asset')||'yield2y',threshold:params.get('threshold')||'1',kind:params.get('kind')||'all',group:params.get('group')||''};
  const store={};
  const element=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const fmt=(n,p=2)=>Number.isFinite(n)?n.toLocaleString('en-GB',{minimumFractionDigits:p,maximumFractionDigits:p}).replace('-','−'):'—';
  const num=n=>fmt(n,0);
  const rate=(a,b)=>Number.isFinite(a)&&b>0?num(a)+' / '+num(b)+' ('+fmt(a*100/b,1)+'%)':'—';
  const interval=arr=>Array.isArray(arr)&&arr.every(Number.isFinite)?arr.map(v=>fmt(v)).join(' to '):'—';
  const note=s=>element('p',s,'ce-small');
  function link(label,url){const a=element('a',label);a.href=url;return a;}
  function detail(label,...content){const d=element('details');d.append(element('summary',label),...content);return d;}
  function selectOptions(s,items,saved){
    const target=s.value||saved;
    s.replaceChildren(...items.map(([v,l])=>new Option(l,v)));s.disabled=!items.length;
    s.value=items.some(([v])=>v===target)?target:items[0]?.[0]||'';
  }
  function table(caption,head,rows){
    const area=element('div',null,'ce-tables');area.tabIndex=0;area.setAttribute('role','region');area.setAttribute('aria-label',caption);
    const t=element('table'),h=element('thead'),tr=element('tr'),body=element('tbody');
    for(const label of head){const th=element('th',label);th.scope='col';tr.append(th);}
    h.append(tr);
    for(const [name,...values] of rows){const r=element('tr'),th=element('th',name);th.scope='row';r.append(th);
      for(const value of values){const td=element('td');td.append(value??'—');r.append(td);}
      body.append(r);
    }
    t.append(element('caption',caption),h,body);area.append(t);return area;
  }
  function eventUrl(date){const id=bank.value==='fed'?'fed-'+date+'-release':'ecb-release-'+date;return 'cross-asset-events.html?'+new URLSearchParams({bank:bank.value,stage:'release',date,event:id});}
  function bookmark(){
    const u=new URL(location.href);u.searchParams.set('bank',bank.value);
    for(const [k,v,def] of [['asset',asset.value,'yield2y'],['threshold',tolerance.value,'1'],['kind',kind.value,'all'],['group',group.value,'']]){
      if(v && v!==def && (bank.value==='ecb'||(k!=='kind'&&k!=='group')))u.searchParams.set(k,v);
      else u.searchParams.delete(k);
    }
    if(bank.value==='fed' && field('fed-group').selectedIndex>0)u.searchParams.set('fedGroup',field('fed-group').value);else u.searchParams.delete('fedGroup');
    history.replaceState(null,'',u);
  }
  function components(){
    const box=field('component-output');box.replaceChildren();
    const d=store.components,b=d?.banks?.[bank.value];if(!b){box.append(note('Joint estimates are unavailable.'));return;}
    selectOptions(asset,Object.entries(b.outcomes).map(([k,v])=>[k,v.label]),initial.asset);
    const fit=b.outcomes[asset.value], sum=b.pairSummary,unit=fit.unit==='%'?'percentage points of return':'bp';
    box.append(note(b.window),element('p',num(fit.n)+' complete releases · '+fit.firstDate+' to '+fit.lastDate+' · '+fit.label+' change in '+unit+'.','pd-stat'));
    const rows=(f)=>[[b.shortLabel,f.short],[b.pathLabel,f.path]].map(([label,x])=>[label,fmt(x?.slopePer5Bp),interval(x?.ci95),fmt(x?.partialRSquared),fmt(x?.conditionalSdBp)]);
    const head=['Instrument moved +5 bp','Asset change','95% interval','Partial R²','Conditional rate SD (bp)'];
    box.append(table('Asset response holding the other instrument fixed',head,rows(fit)));
    box.append(note('Conditional rate SD is the typical residual variation in each rate after accounting for the other. A 5 bp shift can be large relative to this variation. The full model R² is '+fmt(fit.rSquared)+'.'));
    box.append(detail('Paired moves and sensitivity checks',
      note('Both instruments were observed on '+num(sum.n)+' dates. They rose or fell together on '+num(sum.sameSigns)+', moved in opposite directions on '+num(sum.oppositeSigns)+', and at least one was unchanged on '+num(sum.withZero)+'. Correlation was '+fmt(sum.shortPathCorrelation)+'.'),
      table('Asset change per +5 bp in alternative samples',['Sample','Meetings','Near-term rate','95% interval','One-year OIS','95% interval'],[['Exclude largest 5% of moves in either rate',fit.sensitivity],['Common calendar 2004–2025',fit.commonCalendar]].map(([label,f])=>[label,num(f.n),fmt(f.short.slopePer5Bp),interval(f.short.ci95),fmt(f.path.slopePer5Bp),interval(f.path.ci95)]))));
    const examples=b.examples.map(ex=>[ex,b.events.find(e=>e.date===ex.date)]).filter(([,r])=>r).map(([ex,r])=>[ex.reason,link(r.date,eventUrl(r.date)),fmt(r.shortBp),fmt(r.pathBp),fmt(r.residualPathBp)]);
    if(examples.length)box.append(detail('Meetings where the two instruments diverged',table('Selected from the full set of paired releases',['Selection','Meeting','Short (bp)','One-year (bp)','Residual one-year (bp)'],examples),note('Residual one-year repricing is the observed move less the move fitted from the near-term rate change.')));
    if(bank.value==='fed' && d.fedNextMeeting?.frames?.early){
      const e=d.fedNextMeeting,early=e.frames.early,est=early.outcomes[asset.value];
      if(est){
        const extra=detail('Early Fed observations using next-meeting futures',note(e.description),
          table('2000–2003, '+fit.label+' per +5 bp',['Rate instrument','Asset change','95% interval','Paired meetings'],[[e.shortLabel,fmt(est.short.slopePer5Bp),interval(est.short.ci95),num(est.n)],[e.pathLabel,fmt(est.path.slopePer5Bp),interval(est.path.ci95),num(est.n)]]));
        for(const ex of early.examples||[]){
          const line=note(ex.date+' · current-meeting surprise '+fmt(ex.shortBp)+' bp and next-meeting surprise '+fmt(ex.pathBp)+' bp. ');
          line.append(link('Open event window',eventUrl(ex.date)));extra.append(line);
        }
        box.append(extra);
      }
    }
    box.append(detail('Methods and original data',...(d.method||[]).map(note),link('Market database',b.sourceUrl)));
  }
  function reversal(){
    const box=field('reversal-output');box.replaceChildren();const d=store.reversal,b=d?.banks?.[bank.value];
    if(!b){box.append(note('Paired release and conference results are unavailable.'));return;}
    selectOptions(tolerance,b.thresholds.map(t=>[String(t.thresholdBp),t.thresholdBp+' bp']),initial.threshold);
    const s=b.thresholds.find(t=>String(t.thresholdBp)===tolerance.value), threshold=s.thresholdBp;
    box.append(element('p',rate(s.oppositeN,s.directionalN)+' of meetings with moves above '+threshold+' bp in both windows changed direction.','pd-stat'));
    const bar=element('div',null,'pd-partition');bar.setAttribute('aria-hidden','true');
    for(const n of [s.oppositeN,s.reinforceN,s.quietOrSmallN]){const seg=element('span');seg.style.width=(s.pairedN?100*n/s.pairedN:0)+'%';bar.append(seg);}
    box.append(bar,note('Opposite directions '+num(s.oppositeN)+' · same direction '+num(s.reinforceN)+' · at least one small move '+num(s.quietOrSmallN)+' · all paired meetings '+num(s.pairedN)+'.'));
    const c=b.coverage;box.append(note(num(c.officialDecisions)+' historical decisions, '+num(c.releaseEligibleN)+' eligible decision releases and '+num(c.pairedOisN)+' dates with OIS in both windows.'));
    const all=[['Partial giveback',s.partialGivebackN],['Offset to the same size',s.exactOffsetN],['Conference move larger than the initial move',s.netOvertakeN]];
    box.append(table('Relative size when the two moves had opposite signs',['Outcome','Meetings','Among opposite-sign meetings'],all.map(([label,n])=>[label,num(n),rate(n,s.oppositeN)])));
    const assetNames={ois1yBp:'One-year OIS (bp)',yield2yBp:'2Y yield (bp)',slope2s10sBp:'10Y less 2Y (bp)',equityPct:'Equity return (%)'};
    const rows=[];
    for(const [id,label] of [['opposite','Opposite signs'],['reinforce','Same sign']]){
      const stats=s.groups[id];
      for(const [k,name] of Object.entries(assetNames)){
        const cells=['release','conference','combined'].map(st=>{const m=stats?.stages?.[st]?.[k];return m?.n?fmt(m.median)+' ('+num(m.n)+')':'—';});
        rows.push([label+' · '+name,...cells]);
      }
    }
    box.append(detail('Yields, curve and equities by meeting stage',table('Signed median change (observations)',['Group and asset','Release','Conference','Full window'],rows),
      note('The full window uses its own price endpoints. Gaps between the two subwindows can change the final sign.')));
    box.append(note('Among '+num(s.fullWindowN)+' opposite-sign pairs with an observed full window, '+num(s.fullWindowOppositeToReleaseN)+' finished on the opposite side of the initial release move.'));
    if(b.leaders?.length)box.append(detail('Leadership coverage at the fixed 1 bp threshold',
      table('Same-meeting coverage by chair or president',['Leader','Paired meetings','Both moves >1 bp','Opposite signs','Reversal share'],b.leaders.map(l=>[l.leader,num(l.pairedN),num(l.directionalN),num(l.oppositeN),Number.isFinite(l.reversalShare)?fmt(l.reversalShare*100,1)+'%':'—'])),
      note('The share is withheld for leaders with fewer than eight directional meetings.')));
    const current=b.holdout2026?.thresholds.find(v=>v.thresholdBp===threshold);
    if(current)box.append(note('2026 through '+b.holdout2026.through+' · '+num(current.pairedN)+' paired meetings, '+num(current.directionalN)+' with two moves over '+threshold+' bp and '+num(current.oppositeN)+' opposite signs. The historical table ends in 2025.'));
    if(b.examples?.length){
      const examples=b.examples.map(e=>[e.date,fmt(e.releaseOis1yBp),fmt(e.conferenceOis1yBp),fmt(e.combinedOis1yBp),link('Inspect '+e.date,eventUrl(e.date))]);
      box.append(detail('Meetings with large reversals',table('One-year OIS changes (bp)',['Meeting','Release','Conference','Full window','Event record'],examples)));
    }
    box.append(detail('Thresholds, release times and sources',...(d.methods||[]).map(note)));
  }
  function followthrough(){
    const box=field('followthrough'),d=store.followthrough;
    box.replaceChildren();box.hidden=bank.value!=='fed'||!d?.assets?.yield2y||!d?.assets?.slope;
    if(box.hidden)return;
    const threshold=d.primaryThresholdBp;
    const tables=(id)=>d.assets[id].thresholds[String(threshold)].all;
    const two=tables('yield2y'),slope=tables('slope');
    const horizons=[['priorToEvent','Prior fixing to meeting-day fixing'],['priorToNext','Prior fixing to next fixing'],['priorToFifth','Prior fixing to fifth later fixing'],['eventToNext','Meeting-day fixing to next fixing'],['eventToFifth','Meeting-day fixing to fifth later fixing']];
    const rows=horizons.map(([key,label])=>{
      const y=two[key],s=slope[key];
      return [label,rate(y.sameDirection,y.n),num(y.flat),rate(s.sameDirection,s.n),num(s.flat)];
    });
    const links=element('div',null,'ce-links');
    for(const [ext,label] of [['csv','Download matched daily observations (CSV)'],['json','Download thresholds and directional splits (JSON)']]){
      const a=link(label,'data/fed-yield-followthrough.'+ext);a.download='';links.append(a);
    }
    box.append(detail('Did the initial Treasury move persist through the next fixings?',
      note('For each asset, retain moves larger than '+threshold+' bp in absolute size from 10 minutes before to 20 minutes after the scheduled statement. Same direction compares the sign of that move with the change between the two daily Treasury fixings. Flat daily changes remain in the denominator.'),
      table('Direction relative to the scheduled Fed release',['Daily observation interval','2Y same direction','2Y flat','2s10s same direction','2s10s flat'],rows),
      note('The first three intervals include the decision day. The last two measure further movement after the meeting-day fixing. Treasury daily observations are recorded around 15:30 US Eastern time and include other news.'),links));
  }
  function ecbSpeech(){
    const box=field('speech-output');box.replaceChildren();
    field('speech-heading').textContent='Markets around ECB speeches';field('ecb-sources').hidden=false;field('fed-sources').hidden=true;field('fed-controls').hidden=true;
    const d=store.ecbSpeeches;
    field('speech-controls').hidden=!d?.groups?.length;
    if(!d?.groups?.length){box.append(note('ECB speech-window data are unavailable.'));return;}
    const labels={all:'All appearances',year:'Calendar year',leader:'Presidency',decisionRelease:'Compare decision releases',speakerRole:'Speaker role'};
    const kinds=[...new Set(d.groups.map(g=>g.kind))];
    selectOptions(kind,kinds.map(k=>[k,labels[k]||k]),initial.kind);
    const subsets=d.groups.filter(g=>g.kind===kind.value);
    selectOptions(group,subsets.map(g=>[g.label,g.label]),initial.group);
    const g=subsets.find(g=>g.label===group.value),assets=Object.fromEntries(d.assets.map(a=>[a.key,a]));
    box.append(note(num(d.coverage.eligibleEvents)+' eligible appearances across '+num(d.coverage.eligibleDays)+' dates from '+num(d.coverage.allEvents)+' recorded events. Selected sample · '+num(g.nEvents)+' appearances across '+num(g.nDays)+' dates.'));
    if(kind.value==='decisionRelease')box.append(note('The selected group contains standard decision releases. Its price window differs from the speech window.'));
    else box.append(note('Prices compare median quotes 20–10 minutes before the scheduled appearance with median quotes 40–50 minutes afterwards. The rank correlation describes co-movement within these windows.'));
    const dist=g.distribution.map(v=>[assets[v.asset]?.label||v.asset,assets[v.asset]?.unit||'',num(v.n),fmt(v.median),fmt(v.medianAbs),fmt(v.p90Abs)]);
    box.append(table('Price changes around the selected speeches',['Market','Unit','Quotes','Signed median','Median absolute','90th percentile absolute'],dist));
    box.append(table('Paired changes against one-year OIS',['Market','Paired windows','Rank correlation','OIS up >1 bp · median (n)','OIS down >1 bp · median (n)'],
      g.pairs.map(v=>[assets[v.asset]?.label||v.asset,num(v.n),fmt(v.spearman),fmt(v.upMedian)+' ('+num(v.upN)+')',fmt(v.downMedian)+' ('+num(v.downN)+')'])));
    box.append(detail('Repeated dates and large moves',table('Rank correlation checks',['Market','Dates','Paired window ρ','Equal-weighted dates ρ','Largest 1% excluded ρ'],
      g.pairs.map(v=>[assets[v.asset]?.label||v.asset,num(v.nDays),fmt(v.spearman),fmt(v.daySpearman),fmt(v.trimmedSpearman)])),note('The equal-weighted check first averages observations sharing a date. The trimmed check removes the largest absolute OIS changes.')));
    const ev=(d.examples||[]).map(e=>[e.date,e.speaker,e.title,fmt(e.values.ois1y),link('Read communication',e.documentUrl)]);
    if(ev.length)box.append(detail('Largest up and down one-year OIS moves in the full speech sample',table('Eligible speeches with a linked transcript',['Date','Speaker','Title','One-year OIS (bp)','Source'],ev)));
    box.append(detail('Window definitions and eligibility',...(d.method||[]).map(note),
      table('Flags in the full source calendar (may overlap)',['Flag','Appearances'],d.coverage.flags.map(f=>[f.label,num(f.n)])),link(d.source.label,d.source.url)));
  }
  function output(){
    components();reversal();followthrough();if(bank.value==='ecb')ecbSpeech();else fedSpeech();
    reading();
  }
  bank.onchange=()=>{output();bookmark();};
  asset.onchange=()=>{components();bookmark();};tolerance.onchange=()=>{reversal();bookmark();};
  kind.onchange=()=>{group.value='';ecbSpeech();bookmark();};group.onchange=()=>{ecbSpeech();bookmark();};
  function fedSpeech(){
    const box=field('speech-output');box.replaceChildren();const d=store.fedSpeeches,s=field('fed-group');
    field('speech-heading').textContent='Fed Board speeches and SOFR pricing';field('ecb-sources').hidden=true;field('speech-controls').hidden=true;
    field('fed-controls').hidden=!d?.groups?.length;field('fed-sources').hidden=false;
    if(!d?.groups?.length){box.append(note('SOFR pricing observations are unavailable.'));return;}
    selectOptions(s,d.groups.map(g=>[g.label,g.label]),params.get('fedGroup')||d.groups[0].label);
    const selected=d.groups.find(g=>g.label===s.value);
    box.append(note(num(d.coverage.eligible)+' eligible speeches from '+num(d.coverage.catalogue)+' indexed communications · '+num(d.coverage.eligibleSpeakers)+' speakers · '+d.period.firstEvent+' to '+d.period.lastEvent+'. Selected group · '+num(selected.n)+' speeches.'),
      note('These pricing estimates use option-implied quarterly SOFR means. The near contract and a contract starting roughly nine months later are fixed before each speech. Daily observations bracket the appearance and can include other news.'));
    if(Number.isInteger(selected.bothOver1Bp))box.append(element('p',rate(selected.sameDirectionOver1Bp,selected.bothOver1Bp)+' of speeches with moves larger than 1 bp in both quarters had the same direction.','pd-stat'));
    const rows=selected.metrics.map(m=>[m.label,m.unit,num(m.n),fmt(m.median),fmt(m.q25),fmt(m.q75)]);
    box.append(table('Pricing and Treasury comparisons for the selected group',['Measure','Unit','Observations','Median','25th percentile','75th percentile'],rows));
    const benchmark=d.benchmark;
    if(benchmark?.n){
      const near=benchmark.metrics.find(m=>m.key==='nearChangeBp'),deferred=benchmark.metrics.find(m=>m.key==='deferredChangeBp');
      if(near && deferred)box.append(note('Across the full Board sample, '+num(benchmark.n)+' of '+num(benchmark.eligible)+' speeches outside CPI and jobs-report windows matched a comparison date with the same contracts, weekday and window length. The median paired difference in absolute moves (speech minus comparison) was '+fmt(near.medianPairedExcessAbs)+' bp for the near quarter and '+fmt(deferred.medianPairedExcessAbs)+' bp for the deferred quarter.'),
        detail('How the comparison dates were selected',note(benchmark.method)));
    }
    if(d.example?.url)box.append(detail([d.example.date,d.example.speaker,d.example.title].filter(Boolean).join(' · '),note(d.example.description),link('Read source',d.example.url)));
    const sources=element('div',null,'ce-links');for(const src of d.sources||[])sources.append(link(src.label,src.url));
    box.append(detail('Contracts, sample and timing',...(d.methods||[]).map(note),sources));
  }
  field('fed-group').onchange=()=>{fedSpeech();bookmark();};
  async function load(key,name,show){
    try{
      const r=await fetch('data/'+name+'.json');if(!r.ok)throw Error();store[key]=await r.json();
    }catch{store[key]=null;}
    show();
  }
  load('components','policy-path-components',components);
  load('reversal','conference-reversals',reversal);
  load('followthrough','fed-yield-followthrough',followthrough);
  load('ecbSpeeches','speech-market-panel',()=>{if(bank.value==='ecb')ecbSpeech();});
  load('fedSpeeches','fed-speech-pricing-study',()=>{if(bank.value==='fed')fedSpeech();});
  function reading(){
    field('fed-reading').hidden=bank.value!=='fed';field('ecb-reading').hidden=bank.value!=='ecb';
    field('reading-links').href='policy-market-analysis.html?bank='+bank.value+'#headlines';
    field('explorer').href='cross-asset-events.html?bank='+bank.value+'&stage=release';
  }
  reading();
})();
