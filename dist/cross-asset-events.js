(() => {
  'use strict';
  const $ = id => document.getElementById('ce-' + id);
  const numbers = Number.isFinite;
  const bankNames = {fed: 'Federal Reserve', ecb: 'European Central Bank'};
  const state = {bank: 'fed', stage: 'release', leader: '', year: '', lens: '', query: '', asset: '', page: 0, event: ''};
  const pageSize = 8;
  const cache = new Map();
  let requestedMissing = '', events = [], packages = [], filtered = [], scope = [], cohorts = new Map(), news = new Map(), newsAvailable = false, newsMethods = [], chosen = null, loadToken = 0, missingParts = [], speechPartsLoaded = false;
  const params = new URLSearchParams(location.search);
  const mobile = () => window.matchMedia?.('(max-width:680px)').matches;
  const fmtDate = value => value && !isNaN(Date.parse(value + 'T12:00:00Z')) ? new Date(value + 'T12:00:00Z').toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}) : value || '';
  const wanted = key => params.get(key) || '';
  function element(tag, text, className) {
    const n = document.createElement(tag);
    if(text != null) n.textContent = text;
    if(className) n.className = className;
    return n;
  }
  function link(text,url) {
    const a = element('a', text);
    if(url && (/^https?:\/\//i.test(url) || /^[\w-]+\.(html|json|csv)(?:[?#]|$)/.test(url) || /^data\/[\w-]+\.(json|csv)$/.test(url))) a.href = url;
    return a;
  }
  function sign(value, decimals=2) {
    if (!numbers(value)) return '—';
    const abs = Math.abs(value).toFixed(decimals);
    if (value && Number(abs) === 0) return (value > 0 ? '+<' : '−<') + (10**-decimals).toFixed(decimals);
    return (value > 0 ? '+' : value < 0 ? '−' : '') + abs;
  }
  function fmt(value, unit) {return numbers(value) ? sign(value) + (unit === '%' ? '%' : ' ' + unit) : '—';}
  function median(arr) {
    if (!arr.length) return null;
    const a = arr.slice().sort((x,y)=>x-y), mid = Math.floor(a.length/2);
    return a.length%2 ? a[mid] : (a[mid-1]+a[mid])/2;
  }
  function options(select, items, selected) {
    select.replaceChildren(...items.map(([v,t])=>{const o = element('option',t);o.value = v;return o;}));
    select.value = items.some(([v])=>v===selected) ? selected : items[0]?.[0] || '';
    return select.value;
  }
  function data(file) {
    if (!cache.has(file)) {
      const p = fetch('data/'+file+'.json').then(r=>{if(!r.ok) throw Error('File unavailable: '+file);return r.json();});
      cache.set(file,p);
      p.catch(()=>cache.delete(file));
    }
    return cache.get(file);
  }
  function baseUrl(record, page) {
    const q = new URLSearchParams({bank:state.bank,date:record.date});
    if(page==='guidance-shifts') q.set('stage',record.stage);
    return page+'.html?'+q;
  }
  function updateUrl() {
    const q = new URLSearchParams({bank:state.bank,stage:state.stage});
    if(chosen) {q.set('date',chosen.date);q.set('event',chosen.id);}else if(requestedMissing)q.set('event',requestedMissing);
    for(const key of ['leader','year','lens','asset','query']) if(state[key]) q.set(key,state[key]);
    history.replaceState(null,'','?'+q.toString()+location.hash);
  }
  function stageInfo(r) {return r._package.stages?.[r.stage] || {};}
  function stageLabel(r) {return stageInfo(r).label || r.stage;}
  function isSpeech(r) {return r.type==='speech' || ['speech','speechDaily'].includes(r.stage);}
  function isMeeting(r) {return ['release','conference','combined'].includes(r.stage);}
  function meeting(r) {return isMeeting(r) ? cohorts.get(r.date) : null;}
  function reading(r) {
    const m = meeting(r);
    if (numbers(r.score)) {
      const same = r.stage==='release' && m?.sourceType==='conference'?m.releaseReading:m?.sourceType===r.stage?m:null;
      return {score:r.score,evidence:r.evidence || same?.evidence || '',sourceUrl:r.documentUrl || same?.sourceUrl || same?.url};
    }
    if(!m) return null;
    if(r.stage==='release' && m.sourceType==='conference') return m.releaseReading || null;
    if(r.stage===m.sourceType) return {score:m.score,evidence:m.evidence,sourceUrl:m.url};
    return null;
  }
  function labelScore(n) {return n>0?'Hawkish':n<0?'Dovish':'Hold';}
  function newsOf(r) {
    if(!isMeeting(r) && !isSpeech(r)) return [];
    return (news.get(r.date) || []).filter(report=>{
      if (isMeeting(r)) return report.type!=='speech';
      return report.type==='speech' && report.speaker && (r.speaker||r.leader||'').toLocaleLowerCase().includes(report.speaker.toLocaleLowerCase());
    });
  }
  function lensMatch(r) {
    if (!state.lens) return true;
    if (state.lens==='news') return !!newsOf(r).length;
    const n=reading(r)?.score;
    if(!numbers(n)) return false;
    return state.lens==='scored' || (state.lens==='hawk' && n>0) || (state.lens==='dove' && n<0) || (state.lens==='wait' && n===0);
  }
  function chair(r) {return r.leader || meeting(r)?.leader || '';}
  function stageTitle(r) {
    const name = r.speaker || (isSpeech(r) ? r.leader : '');
    return isSpeech(r) ? [name,r.title].filter(Boolean).join(' · ') || stageLabel(r) : stageLabel(r);
  }
  function pick(record) {
    if(!record) return;
    requestedMissing='';
    chosen=record;state.event=record.id;
    const ix=filtered.indexOf(record);
    if(ix>=0) state.page=Math.floor(ix/pageSize);
    if(mobile()) $('index').open=false;
    index(); detail(); updateUrl();
  }
  function syncStage(next,preferred) {
    state.stage=next;
    const rows=events.filter(r=>r.stage===state.stage);
    const names=[...new Set(rows.map(chair).filter(Boolean))].sort();
    state.leader=options($('leader'),[['','All tenures'],...names.map(n=>[n,n])],state.leader);
    const years=[...new Set(rows.map(r=>r.date.slice(0,4)))].sort().reverse();
    state.year=options($('year'),[['','All years'],...years.map(y=>[y,y])],state.year);
    $('stage').value=state.stage;
    refresh(preferred);
  }
  function refresh(preferred) {
    scope=events.filter(r=>r.stage===state.stage && (!state.leader||chair(r)===state.leader) && (!state.year||r.date.startsWith(state.year)) && lensMatch(r));
    const q=state.query.toLocaleLowerCase().trim();
    filtered=scope.filter(r=>!q||[r.title,chair(r),r.speaker,r.date,fmtDate(r.date)].some(v=>v?.toLocaleLowerCase().includes(q)));
    const next=requestedMissing?null:(filtered.find(r=>r.id===preferred) || filtered.find(r=>r.date===preferred) || filtered[0]);
    state.page=0;
    if(next) {
      chosen=next;state.event=next.id;state.page=Math.floor(filtered.indexOf(chosen)/pageSize);
    } else {chosen=null;state.event='';}
    $('status').textContent=filtered.length.toLocaleString()+' '+(filtered.length===1?'window':'windows')+' in this selection.'+(state.stage==='speech'&&missingParts.length?' Speech data are incomplete. Missing periods: '+missingParts.map(name=>name.match(/\d{4}-\d{4}/)?.[0]||name).join(', ')+'.':'');
    index();detail();updateUrl();
  }
  function index() {
    const list=$('events');list.replaceChildren();
    for(const r of filtered.slice(state.page*pageSize,(state.page+1)*pageSize)) {
      const b=element('button',null,'ce-event');b.type='button';b.setAttribute('aria-current',String(r===chosen));
      b.append(element('strong',fmtDate(r.date)+(r.time?' · '+r.time:'')),element('small',r.speaker || chair(r) || stageLabel(r)));
      if(isSpeech(r) && r.title) b.append(element('small',r.title));
      b.onclick=()=>pick(r);list.append(b);
    }
    const pages=Math.ceil(filtered.length/pageSize);
    $('page').textContent=pages?(state.page+1)+' / '+pages:'0 / 0';
    $('prev').disabled=state.page<=0;$('next').disabled=state.page+1>=pages;
  }
  function related(r) {
    if (!isMeeting(r)) return [r];
    const order=['release','conference','combined'];
    return events.filter(e=>e.date===r.date && isMeeting(e)).sort((a,b)=>order.indexOf(a.stage)-order.indexOf(b.stage));
  }
  function stageMenu(box,r,legs) {
    if(legs.length<2) return;
    const nav=element('div',null,'ce-stage-links');nav.setAttribute('aria-label','Meeting windows');
    for(const e of legs) {
      const b=element('button',stageLabel(e));b.type='button';b.setAttribute('aria-pressed',String(e===r));
      b.onclick=()=>{
        if (!lensMatch(e)) {state.lens='';$('lens').value='';}
        syncStage(e.stage,e.id);
      };nav.append(b);
    }
    box.append(nav);
  }
  function policy(box,r) {
    const m=meeting(r), view=reading(r);
    if(!m && !isSpeech(r) && !view && !r.documentUrl) return;
    const section=element('section');section.append(element('h3',r.stage==='minutes'?'Minutes and source text':'Guidance and prior pricing'));
    const values=element('dl',null,'ce-readings');
    const add=(k,v)=>{const div=element('div');div.append(element('dt',k),element('dd',v));values.append(div);};
    if(numbers(view?.score)) add('Text in this window',labelScore(view.score)+' ('+sign(view.score,0)+')');
    if(m) {
      add(state.bank==='ecb'?'Deposit rate decision':'Policy rate decision',fmt(m.actionBp,'bp'));
      if(numbers(m.priorMoveBp)) add(m.priorIsProxy?'Pre-meeting MRO estimate':'Move priced for the decision',fmt(m.priorMoveBp,'bp'));
      if(numbers(m.pricingGapBp)) add('Decision less priced move',fmt(m.pricingGapBp,'bp'));
    }
    if(values.children.length) section.append(values);
    if(view?.evidence) section.append(element('p',view.evidence));
    else if(!numbers(view?.score)) section.append(element('p',r.stage==='combined'?'The combined window spans both statements. Select a publication window to inspect its text score.':'No forward-rate score has been assigned to this communication.','ce-small'));
    if(m?.priorMethod) section.append(element('p',m.priorMethod,'ce-small'));
    if(m?.priorPricingNote) section.append(element('p',m.priorPricingNote,'ce-small'));
    const links=element('div',null,'ce-links');
    const original=r.documentUrl || view?.sourceUrl || (r.stage==='release'?m?.releaseUrl:null);
    if(original) links.append(link('Original communication',original));
    if(m) {
      links.append(link('Meeting, cycle and pricing evidence',baseUrl(r,'stance-history')));
      if(r.stage==='release' || (r.stage==='conference' && state.bank==='ecb')) links.append(link('Guidance versus the previous meeting',baseUrl(r,'guidance-shifts')));
    } else if(isSpeech(r)) links.append(link('Speech research',state.bank==='fed'?'fed-leader-speeches.html?date='+r.date+'#archive':'ecb-speech-stance.html#evidence'));
    if(m?.priorPricingSource)links.append(link('Pricing source',m.priorPricingSource));
    if(links.children.length) section.append(links);
    box.append(section);
  }
  function assetsOf(r) {return r._package.assets || [];}
  function assetTable(box,r,legs) {
    const section=element('section');section.append(element('h3','Market moves'));
    function table(items) {
      const wrap=element('div',null,'ce-tables');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label','Changes across markets and event windows');
      const t=element('table'), header=element('thead'), tr=element('tr');
      tr.append(element('th','Instrument'));
      for(const e of legs){const th=element('th',legs.length>1?stageLabel(e):'Change','ce-num'+(r===e?' ce-selected':''));th.scope='col';tr.append(th);}
      header.append(tr);t.append(header);
      const body=element('tbody');
      for(const a of items) {
        const row=element('tr');const th=element('th',a.label);th.scope='row';row.append(th);
        for(const e of legs) {
          const v=e.values?.[a.id];
          row.append(element('td',fmt(v,a.unit),'ce-num '+(numbers(v)?(e===r?'ce-selected':''):'ce-null')));
        }
        body.append(row);
      }
      t.append(body);wrap.append(t);return wrap;
    }
    const assets=assetsOf(r), main=['ois1y','yield2y','yield10y','slope','italySpread10y','equity','usEquityDaily','bankEquity','eurusd','usdjpy','vixDaily'];
    const chosenAssets=main.map(id=>assets.find(v=>v.id===id)).filter(Boolean);
    const other=assets.filter(a=>!chosenAssets.includes(a));
    const mainMoves=['ois1y','yield2y','slope','equity','eurusd','usEquityDaily']
      .map(id=>assets.find(asset=>asset.id===id))
      .filter(asset=>asset && numbers(r.values?.[asset.id])).slice(0,3);
    if(mainMoves.length){
      const reading=mainMoves.map(asset=>asset.label+' '+fmt(r.values[asset.id],asset.unit)).join(' · ');
      section.append(element('p',reading,'study-result'));
    }
    section.append(table(chosenAssets.length?chosenAssets:assets));
    if(chosenAssets.length && other.length){const more=element('details',null,'ce-more');more.append(element('summary','See '+other.length+' more instruments'),table(other));section.append(more);}
    section.append(element('p',legs.length>1?'The whole-meeting change uses its own start and end quotes. A dash marks a missing quote. A quoted zero is shown as zero.':'A dash marks a missing quote. A quoted zero is shown as zero.','ce-small'));
    const methods=element('details');methods.append(element('summary','Instruments and sign conventions'));
    for(const a of assetsOf(r)) if(a.description) methods.append(element('p',a.label+' · '+a.description,'ce-small'));
    const source=r._package.source;
    const refs=element('div',null,'ce-links');if(source?.url) refs.append(link(source.label || 'Market source',source.url));
    const partForDate=(r._package.parts||[]).find(name=>{const years=name.match(/(\d{4})-(\d{4})/);return years&&r.date.slice(0,4)>=years[1]&&r.date.slice(0,4)<=years[2];});
    refs.append(link('Download event observations (JSON)','data/'+(isSpeech(r)&&partForDate?partForDate:r._file)+'.json'));methods.append(refs);
    section.append(methods);
    if(Array.isArray(r.path) && r.path.length) {
      const area=element('div',null,'ce-tables'), t=element('table'), h=element('thead'), row=element('tr'),body=element('tbody');
      area.tabIndex=0;area.setAttribute('role','region');area.setAttribute('aria-label','Returns through the event');
      const present=assetsOf(r).filter(a=>r.path.some(p=>numbers(p.values?.[a.id])));
      row.append(element('th','Minutes from start'));
      for(const a of present)row.append(element('th',a.label,'ce-num'));
      h.append(row);t.append(element('caption','Cumulative price changes from five minutes before the start.'),h);
      for(const point of r.path) {const row=element('tr');row.append(element('th',point.minutes===0?'At the start':'+'+point.minutes+' min'));
        for(const a of present)row.append(element('td',fmt(point.values?.[a.id],a.unit),'ce-num'));body.append(row);}
      t.append(body);area.append(t);section.append(element('h4','How prices evolved'),area);
    }
    box.append(section);
  }
  function liveTiming(r,report) {
    if(report.recordKind!=='live entry'||!report.publishedAt||!/^\d{2}:\d{2}$/.test(r.time)||!r.timeZone||['combined','speechDaily'].includes(r.stage))return '';
    try {
      const fields=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:r.timeZone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date(report.publishedAt)).filter(f=>f.type!=='literal').map(f=>[f.type,f.value]));
      if([fields.year,fields.month,fields.day].join('-')!==r.date)return '';
      const [h,m]=r.time.split(':').map(Number);
      const gap=Number(fields.hour)*60+Number(fields.minute)+Number(fields.second)/60-h*60-m;
      const abs=Math.abs(gap), elapsed=abs<1?'less than one minute':Math.round(abs)+' min';
      return fields.hour+':'+fields.minute+':'+fields.second+' local · '+(gap===0?'at the recorded start':elapsed+(gap>0?' after':' before')+' the '+stageLabel(r).toLowerCase()+' start');
    } catch {return '';}
  }
  function discoveryCoverage(catalogue,reports) {
    const box=$('discovery');
    box.replaceChildren();
    box.hidden=!Number.isInteger(catalogue?.allRows);
    if(box.hidden) return;
    const count=n=>n.toLocaleString('en-GB');
    box.append(element('h3','What the archive contains'));
    box.append(element('p','Across all jurisdictions the archive contains '+count(catalogue.allRows)+' candidate records. '+count(catalogue.fourOutletRows)+' are attributed to Reuters, Bloomberg, the Financial Times or The Wall Street Journal.','ce-small'));
    const tags=catalogue.fourOutletDirectScope;
    if(tags) {
      const tagged=tags.fedOnly+tags.ecbOnly+tags.both;
      if(Number.isInteger(tagged)) box.append(element('p',count(tagged)+' records attributed to those publishers have a matching publisher domain and a US or euro-area tag. The tags identify jurisdictions. An event match also requires checking the headline, date and central-bank communication.','ce-small'));
    }
    const publishers=catalogue.publishers||{};
    const published=new Map((reports||[]).map(r=>[r.url,r.publisher]));
    const overlap=catalogue.siteOverlap;
    if(reports && overlap?.curatedRows===reports.length && Number.isInteger(overlap.matchedSiteRows)) {
      box.append(element('p',count(overlap.matchedSiteRows)+' of '+count(reports.length)+' reviewed event–article links match an archive record by headline ID or article URL. A joint report can link to two events.','ce-small'));
    }
    const counts=new Map();
    for(const publisher of published.values()) counts.set(publisher,(counts.get(publisher)||0)+1);
    const table=element('table'), header=element('thead'), headings=element('tr'), body=element('tbody');
    table.append(element('caption','The archive counts discovery records across jurisdictions. The Fed and ECB website sample counts distinct reviewed article links, including additional source research.'));
    for(const label of ['Publisher','Archive records','Fed and ECB articles']) {const th=element('th',label);th.scope='col';headings.append(th);}
    header.append(headings);
    for(const name of ['Reuters','Bloomberg','Financial Times','The Wall Street Journal']) {
      const archive=publishers[name]??(name==='The Wall Street Journal'?publishers['Wall Street Journal']:null);
      const tr=element('tr'), th=element('th',name);th.scope='row';
      tr.append(th,element('td',Number.isInteger(archive?.rows)?count(archive.rows):'—','ce-num'),element('td',reports?count(counts.get(name)||0):'—','ce-num'));
      body.append(tr);
    }
    table.append(header,body);
    const download=link('Download archive counts and definitions (JSON)','data/news-catalogue-summary.json');
    download.download='';
    box.append(table,download);
  }
  function selectionCoverage(selection) {
    const box=$('selection');
    box.replaceChildren();
    box.hidden=!selection;
    if(box.hidden) return;
    box.append(element('h3','Which meetings have news coverage?'));
    if(selection.byAction?.length) {
      const labels={cut:'Cuts',hold:'Holds',hike:'Hikes'};
      const rates=selection.byAction.map(v=>{
        const label=labels[v.action]||v.action;
        return label+' '+v.covered+' of '+v.total+(v.total?' ('+(100*v.covered/v.total).toFixed(1)+'%)':'');
      });
      box.append(element('p',bankNames[state.bank]+' decisions with a verified headline · '+rates.join(' · '),'ce-small'));
    }
    const study=selection.yieldStudy;
    if(study) {
      const groups=[['all eligible meetings',study.all],['with verified headlines',study.covered],['without verified headlines',study.uncovered]];
      const medians=groups.filter(([,v])=>Number.isInteger(v?.n)).map(([label,v])=>label+' '+(Number.isFinite(v.medianAbsBp)?v.medianAbsBp.toFixed(2)+' bp':'—')+' (n = '+v.n+')');
      if(medians.length) {
        box.append(element('p','Among meetings with an observed quote, the median absolute change in '+[study.instrument,study.window,study.period].filter(Boolean).join(' · ')+' was as follows. '+medians.join(' · ')+'.','ce-small'));
      }
    }
    box.append(link('Selection audit and definitions (JSON)','data/news-coverage-audit.json'));
  }
  function annualNewsCoverage(asOf,audit,catalogue,reports) {
    const panel=$('news-coverage'), region=$('coverage-table');
    region.replaceChildren();
    discoveryCoverage(catalogue,reports);
    selectionCoverage(audit?.banks?.[state.bank]?.selection);
    panel.hidden=!newsAvailable && $('discovery').hidden && $('selection').hidden;
    if(location.hash==='#ce-news-coverage')panel.open=true;
    $('news-picker').hidden=!newsAvailable;
    $('year-headlines').hidden=!newsAvailable;
    if (!newsAvailable) {
      $('coverage-title').textContent='News archive and verified coverage';
      $('coverage-method').hidden=true;
      region.append(element('p','The event-linked headline file is unavailable.','ce-small'));
      return;
    }
    const outlets = [['Reuters','Reuters'],['Bloomberg','Bloomberg'],['Financial Times','FT'],['The Wall Street Journal','WSJ']];
    const rows = [...news.values()].flat();
    const lastYear = Math.max(2026, Number(asOf?.slice(0,4)) || 0, ...rows.map(r=>Number(r.date.slice(0,4))));
    const years = new Map();
    for (let year=2000; year<=lastYear; year++) {
      years.set(year,{decisions:new Set(),speeches:new Set(),headlines:0,publishers:new Map()});
    }
    for (const r of rows) {
      const y=years.get(Number(r.date.slice(0,4)));
      if (!y) continue;
      if (r.type==='speech') y.speeches.add(r.date+'|'+r.speaker);
      else y.decisions.add(r.date);
      y.headlines++;
      y.publishers.set(r.publisher,(y.publishers.get(r.publisher)||0)+1);
    }
    $('coverage-title').textContent=bankNames[state.bank]+' news coverage by year · 2000–'+lastYear;
    const byEvent=new Map();
    for(const report of rows) {
      const key=[report.date,report.type,report.speaker||''].join('|');
      if(!byEvent.has(key))byEvent.set(key,new Set());
      byEvent.get(key).add(report.publisher);
    }
    const shared=[...byEvent.values()].filter(outlets=>outlets.size>1).length;
    region.append(element('p',rows.length+' headlines cover '+byEvent.size+' distinct events. '+shared+' events have coverage from two or more of the four publishers.','ce-small'));
    const frame=audit?.banks?.[state.bank];
    const frameYears=new Map((frame?.years||[]).map(y=>[Number(y.year),y]));
    const hasFrame=frameYears.size>0;
    const method=$('coverage-method'), notes=$('coverage-notes');
    method.hidden=!hasFrame;
    notes.replaceChildren();
    if(hasFrame) {
      const scope=Array.isArray(frame.scope)?frame.scope:[frame.scope];
      for(const line of scope) if(typeof line==='string' && line) region.append(element('p',line,'ce-small'));
      for(const line of audit.method||[]) if(typeof line==='string' && line) notes.append(element('p',line,'ce-small'));
      if(frame.unmatchedNewsCount>0) notes.append(element('p','News links outside this event universe: '+frame.unmatchedNewsCount+'. The coverage rates use matched events only.','ce-small'));
    } else {
      region.append(element('p','Event totals are unavailable. The table shows reviewed events and publisher counts.','ce-small'));
    }
    const table=element('table'), header=element('thead'), headings=element('tr'), body=element('tbody');
    table.append(element('caption',hasFrame?'Coverage shows tracked decisions and leader speeches with verified news divided by the yearly event total. Comparable pricing supports subtracting the priced move from the decision. A dash marks an unavailable measure or a rate with no eligible events. Publisher columns count headlines.':'Counts use the event year. Decisions and speeches count distinct events with verified coverage. Publisher columns count headlines.'));
    const columns=hasFrame?['Decisions with news','Speeches with news','Decisions with 2+ outlets','Decisions with comparable pricing','Decisions with news and comparable pricing']:['Decisions','Speeches'];
    for (const title of ['Year',...columns,'Headlines',...outlets.map(([,label])=>label)]) {
      const th=element('th',title); th.scope='col'; headings.append(th);
    }
    header.append(headings);
    const rate=new Intl.NumberFormat('en-GB',{style:'percent',maximumFractionDigits:1});
    const fraction=(covered,total)=>{
      if (!Number.isInteger(covered)||!Number.isInteger(total)) return '—';
      return covered+' / '+total+' ('+(total?rate.format(covered/total):'—')+')';
    };
    for (const [year,y] of [...years].reverse()) {
      const tr=element('tr'), th=element('th',String(year)); th.scope='row'; tr.append(th);
      const yearFrame=frameYears.get(year);
      const coverage=hasFrame?[fraction(yearFrame?.decisionWithNews,yearFrame?.decisionTotal),fraction(yearFrame?.speechWithNews,yearFrame?.speechTotal),yearFrame?.multiDecision,yearFrame?.pricedDecision,yearFrame?.matchedPricedDecision]:[y.decisions.size,y.speeches.size];
      for (const value of [...coverage,y.headlines,...outlets.map(([name])=>y.publishers.get(name)||0)]) {
        tr.append(element('td',String(value??'—'),'ce-num'));
      }
      body.append(tr);
    }
    table.append(header,body); region.append(table);
    const picker=$('news-year'), listing=$('year-headlines');
    picker.replaceChildren();
    for(const year of [...years.keys()].reverse())picker.append(new Option(String(year),String(year)));
    picker.value=years.has(Number(state.year)) ? state.year : String(lastYear);
    const showYear=()=>{
      listing.replaceChildren();
      const selected=rows.filter(row=>row.date.startsWith(picker.value));
      if(!selected.length) {
        listing.append(element('p','No reviewed headline for this bank and year.','ce-small'));
        return;
      }
      const list=element('table'), head=element('thead'), tr=element('tr'), body=element('tbody');
      list.append(element('caption',bankNames[state.bank]+' · '+picker.value+' · '+selected.length+' reviewed headlines'));
      for(const label of ['Event date','Communication','Publication date','Publisher','Headline reading']) tr.append(element('th',label));
      head.append(tr);
      for(const row of selected.sort((a,b)=>a.date.localeCompare(b.date)||a.publisher.localeCompare(b.publisher))) {
        const line=element('tr'), reading=element('td');
        reading.append(link(row.angle,row.url));
        line.append(element('td',row.date),element('td',row.speaker||'Decision'),element('td',row.publicationDate),element('td',row.publisher),reading);
        body.append(line);
      }
      list.append(head,body);listing.append(list);
    };
    picker.onchange=showYear;
    showYear();
  }
  function articles(box,r) {
    const section=element('section');section.id='ce-publisher-reports';section.append(element('h3','How the news framed it'));
    const items=newsOf(r);
    const sample=[...news.values()].flat();
    const coverage=element('details',null,'ce-more');
    if(sample.length) {
      coverage.append(element('summary','What do the sampled headlines cover?'));
      const sets=new Set(sample.map(x=>x.date+'|'+x.type+'|'+(x.speaker||'')));
      const count=match=>sample.filter(match).length;
      const classifications=[['Any immediate rate action',count(x=>!!x.action)],['Forward policy level',count(x=>x.pathBasis==='level')],['Revision to earlier guidance or expectations',count(x=>x.pathBasis==='revision')],['Conditional or open path',count(x=>x.pathBasis==='open')],['No coded forward path',count(x=>!x.path)]];
      const t=element('table'),h=element('thead'),hr=element('tr'),body=element('tbody');
      t.append(element('caption',sample.length+' coded headlines on '+sets.size+' '+bankNames[state.bank]+' events. Action and path can appear in the same headline.'));
      hr.append(element('th','Headline content'),element('th','Count'));h.append(hr);t.append(h);
      for(const [title,n] of classifications) {const row=element('tr');row.append(element('th',title),element('td',String(n)));body.append(row);}
      t.append(body);coverage.append(t,element('p','These selected events have recoverable publisher records. Several reports can cover one event. The counts describe these headlines.','ce-small'),link('Browse events with news evidence','cross-asset-events.html?bank='+state.bank+'&stage=release&lens=news'));
    }
    if(!items.length) {
      section.append(element('p',newsAvailable?'No original Bloomberg, Wall Street Journal, Financial Times or Reuters headline has been verified for this event.':'The news evidence file could not be loaded.','ce-small'));if(sample.length)section.append(coverage);box.append(section);return;
    }
    section.append(element('p','Headlines are reviewed on Bloomberg, The Wall Street Journal, Financial Times and Reuters. Each summary links to the original publisher. Meeting-day coverage can span both the release and the press conference. Each item identifies the available publication or live-entry time. Headline alignment with a market move is descriptive.','ce-small'));
    const more=element('details',null,'study-reference');
    if(items.length>2)more.append(element('summary','Read '+(items.length-2)+' more '+(items.length===3?'report':'reports')+' for this event'));
    for(const [index,report] of items.entries()) {
      const article=element('article',null,'ce-article');article.append(element('p',[report.publisher,report.recordKind,report.coverageMode,report.evidenceKind].filter(Boolean).join(' · '),'ce-time'),element('h4',report.angle));
      if(report.excerpt)article.append(element('p','Words in the published title · “'+report.excerpt+'”','ce-small'));
      const timing=liveTiming(r,report);if(timing)article.append(element('p',timing,'ce-small'));
      const path = report.path ? ({
        tighter: report.pathBasis==='revision'?'less easing or more tightening than previously expected':'tighter policy ahead',
        easier: report.pathBasis==='revision'?'more easing or less tightening than previously expected':'easier policy ahead',
        steady:'steady policy ahead',conditional:'conditional or open',mixed:'mixed signals'
      }[report.path]||report.path) : 'no forward direction stated';
      section.dataset.hasNews='true';
      article.append(element('p',[report.action?'Decision in title: '+report.action:null,'Policy path: '+path,report.focus].filter(Boolean).join(' · '),'ce-small'));
      const sourceLinks=element('div',null,'ce-links');sourceLinks.append(link('Read the published title',report.url));
      if(report.evidenceUrl && report.evidenceUrl!==report.url) sourceLinks.append(link('Publisher evidence',report.evidenceUrl));
      article.append(sourceLinks);
      const times=[];
      if(report.publishedAt) times.push('Publisher’s publication time '+report.publishedAt);else if(report.publicationDate) times.push('Publication date '+report.publicationDate);
      if(report.editionAt) times.push('Edition or feed time '+report.editionAt);
      if(report.updatedAt) times.push('Updated '+report.updatedAt);
      if(report.decisionReleaseAt && numbers(report.secondsFromDecision))times.push('Official decision release '+report.decisionReleaseAt+' · live dispatch '+Math.abs(report.secondsFromDecision)+' seconds '+(report.secondsFromDecision<0?'before':'after')+' the release');
      if(report.versionNote) times.push(report.versionNote);
      if(Array.isArray(report.markets)&&report.markets.length) article.append(element('p','Market moves named in the headline · '+report.markets.map(m=>m.asset+' '+m.direction).join(', '),'ce-small'));
      if(times.length) {const t=element('details');t.append(element('summary','Timestamp and version'),element('p',times.join(' · '),'ce-small'));if(report.decisionClockSource)t.append(link('Official release clock',report.decisionClockSource));article.append(t);}
      (index<2?section:more).append(article);
    }
    if(items.length>2)section.append(more);
    if(sample.length)section.append(coverage);
    const methods=element('details');methods.append(element('summary','Headline sample and coding'));for(const line of newsMethods)methods.append(element('p',line,'ce-small'));methods.append(link('Download headline coding and sources','data/news-framing.json'));section.append(methods);box.append(section);
  }
  const SVG = 'http://www.w3.org/2000/svg';
  function svg(tag,attrs,text) {
    const e=document.createElementNS(SVG,tag);
    for(const [key,val] of Object.entries(attrs))e.setAttribute(key,String(val));
    if(text!=null)e.textContent=text;return e;
  }
  function distribution(box,r) {
    const section=element('section');
    section.id='ce-distribution';section.append(element('h3','The same market across events'));
    const label=element('label','Market','ce-chart-select'), control=element('select');label.append(control);section.append(label);
    const assets=assetsOf(r);
    state.asset=options(control,assets.map(a=>[a.id,a.label]),assets.some(a=>a.id===state.asset)?state.asset:assets.find(a=>a.id==='yield2y')?.id||assets[0]?.id);
    const output=element('div');section.append(output);
    const rows=scope.filter(e=>e.groupEligible===true && e._file===r._file);
    function plot() {
      output.replaceChildren();
      const a=assets.find(a=>a.id===state.asset);if(!a)return;
      const vals=rows.filter(e=>numbers(e.values?.[a.id])).map(e=>({e,v:e.values[a.id],t:Date.parse(e.date+'T12:00Z')}));
      const dates=vals.map(x=>x.t), amounts=vals.map(x=>x.v);
      const selected=vals.find(x=>x.e.id===r.id);
      const positive=amounts.filter(v=>v>0).length,negative=amounts.filter(v=>v<0).length,flat=amounts.length-positive-negative;
      output.append(element('p',vals.length.toLocaleString()+' eligible '+stageLabel(r).toLowerCase()+' windows with '+a.label+' observations. The comparison uses the current filters. Searching the event index leaves this comparison intact.','ce-small'));
      if(!vals.length)return;
      const results=element('dl',null,'ce-readings');
      for(const [k,v] of [['Selected event',fmt(r.values?.[a.id],a.unit)],['Median change',fmt(median(amounts),a.unit)],['Median absolute change',Math.abs(median(amounts.map(Math.abs))).toFixed(2)+(a.unit==='%'?'%':' '+a.unit)],['Up / down / flat',positive+' / '+negative+' / '+flat]]) {
        const item=element('div');item.append(element('dt',k),element('dd',v));results.append(item);
      }
      output.append(results);
      const comparison=events.filter(e=>e._file===r._file && e.stage===r.stage && e.groupEligible===true && (!state.leader||chair(e)===state.leader) && (!state.year||e.date.startsWith(state.year)) && (state.lens!=='news'||newsOf(e).length) && numbers(e.values?.[a.id]) && numbers(reading(e)?.score));
      if(comparison.length) {
        const wrap=element('details',null,'ce-more'), t=element('table'),h=element('thead'),row=element('tr'),body=element('tbody');
        wrap.append(element('summary','Compare hawkish, dovish and hold guidance'));
        for(const k of ['Text reading','Windows','Median change','Median absolute change'])row.append(element('th',k));
        h.append(row);t.append(element('caption','Eligible '+stageLabel(r).toLowerCase()+' windows by text reading, using the selected year and tenure.'),h);
        for(const [group,n] of [['Hawkish',1],['Hold',0],['Dovish',-1]]) {
          const selected=comparison.filter(e=>Math.sign(reading(e).score)===n).map(e=>e.values[a.id]);
          const tr=element('tr');tr.append(element('th',group),element('td',String(selected.length)),element('td',fmt(median(selected),a.unit)),element('td',selected.length?Math.abs(median(selected.map(Math.abs))).toFixed(2)+(a.unit==='%'?'%':' '+a.unit):'—'));body.append(tr);
        }
        t.append(body);wrap.append(t,element('p','Each group includes only events with explicit guidance and a quote for this market. Economic conditions and other news can differ across groups.','ce-small'));output.append(wrap);
      }
      if(vals.length<2) return;
      let lo=Math.min(0,...amounts),hi=Math.max(0,...amounts);
      if(hi===lo){hi+=1;lo-=1;}
      const t0=Math.min(...dates),t1=Math.max(...dates);
      const xx=t=>t1===t0?373:69+(t-t0)/(t1-t0)*616;
      const yy=v=>16+(hi-v)/(hi-lo)*142;
      const figure=element('figure');
      const s=svg('svg',{class:'ce-chart',viewBox:'0 0 710 188',role:'img','aria-label':a.label+' change by event date, '+fmt(lo,a.unit)+' to '+fmt(hi,a.unit)});
      const ticks=[hi,...(hi>0&&lo<0?[0]:[]),lo];
      for(const v of ticks){
        const y=yy(v);
        s.append(svg('line',{x1:69,x2:685,y1:y,y2:y,class:v===0?'ce-zero':'ce-grid'}));
        s.append(svg('text',{x:62,y:y+4,'text-anchor':'end'},sign(v,Math.abs(v)>=10?1:2)));
      }
      s.append(svg('path',{class:'ce-dots',d:vals.map(x=>'M'+xx(x.t).toFixed(1)+' '+yy(x.v).toFixed(1)+'l.01 0').join(' ')}));
      if(selected)s.append(svg('circle',{class:'ce-spot',cx:xx(selected.t),cy:yy(selected.v),r:5}));
      for(const [time,loc,anchor] of [[t0,69,'start'],[t1,685,'end']]) s.append(svg('text',{x:loc,y:181,'text-anchor':anchor},fmtDate(new Date(time).toISOString().slice(0,10))));
      figure.append(s,element('figcaption','Each dot is one change in '+a.unit+' during the selected kind of window.'+(selected?' The rust-coloured dot is the selected event.':' The selected event has no eligible observation for this comparison.')));
      output.append(figure);
    }
    control.onchange=()=>{state.asset=control.value;plot();updateUrl();};plot();box.append(section);
  }
  function detail() {
    const box=$('detail');box.replaceChildren();
    const r=chosen;
    if(!r) {box.append(element('h2',requestedMissing?'Requested event unavailable':'No matching events'),element('p',requestedMissing?'The requested event is absent from the loaded observations. Select another date from the index or retry this link.':'Change the filters or search terms to see recorded windows.'));return;}
    box.append(element('p',[bankNames[state.bank],fmtDate(r.date),r.time ? r.time+' '+(r.timeZone || r._package.timezone || '') : null].filter(Boolean).join(' · '),'ce-time'),element('h2',stageTitle(r)));
    const titleInfo=[isSpeech(r)?null:chair(r),isSpeech(r)?stageLabel(r):null].filter(Boolean).join(' · ');
    if(titleInfo)box.append(element('p',titleInfo));
    const legs=related(r);
    stageMenu(box,r,legs);
    if(r.window || stageInfo(r).window)box.append(element('p',r.window || stageInfo(r).window,'ce-small'));
    if(r.startUtc && r.endUtc)box.append(element('p','UTC quote endpoints · '+r.startUtc+' to '+r.endUtc,'ce-small'));
    if(r.timeSource){const meta=element('p',null,'ce-small');meta.append(link(r.timeEvidence?'Published release time · '+r.timeEvidence:'Published release time',r.timeSource));box.append(meta);}
    const flags=Array.isArray(r.flags)?r.flags:[];
    if(flags.length || r.groupEligible===false) box.append(element('p',(flags.length?flags.join(' · ')+'. ':'')+(r.groupEligible===false?'This observation is excluded from the comparison across events.':''),'ce-note ce-small'));
    assetTable(box,r,legs);
    distribution(box,r);
    const readingPanels=element('div',null,'ce-reading-panels'), official=element('div'), press=element('div');
    policy(official,r);
    if(window.CBIPolicyTools?.render) {const tools=element('div');official.append(tools);window.CBIPolicyTools.render(tools,{...r,bank:state.bank});}
    articles(press,r);if(official.children.length)readingPanels.append(official);readingPanels.append(press);box.append(readingPanels);
    if(window.CBICommodityContext?.render) {
      const energy=element('section');energy.id='commodity-event-day';box.append(energy);window.CBICommodityContext.render(energy,r.date);
    }
    const methods=element('details',null,'ce-method');methods.append(element('summary','Dataset and measurement'));
    const file=r._package;
    for(const p of (Array.isArray(file.method)?file.method:typeof file.method==='string'?[file.method]:[]))methods.append(element('p',p,'ce-small'));
    const info=element('div',null,'ce-links');
    if(file.source?.url)info.append(link(file.source.label||'Market database',file.source.url));
    if(file.source?.methodologyUrl)info.append(link('Source methodology',file.source.methodologyUrl));
    const otherSources=Array.isArray(file.sources)?file.sources:Object.entries(file.sources||{}).map(([label,data])=>typeof data==='string'?{label,url:data}:data);
    for(const src of otherSources) if(src && typeof src==='object' && src.url && src.url!==file.source?.url)info.append(link(src.label||src.name||'Additional source',src.url));
    info.append(link(file.parts?.length?'Download meeting observations and speech index':'Download observations','data/'+r._file+'.json'));
    for(const part of file.parts||[])info.append(link('Speech data '+(part.match(/\d{4}-\d{4}/)?.[0]||part),'data/'+part+'.json'));methods.append(info);box.append(methods);
  }
  async function loadBank(bank,preferred) {
    const ticket=++loadToken;
    state.bank=bank;
    $('bank').value=bank;
    $('news-coverage').hidden=true;
    $('layout').hidden=true;$('status').textContent='Loading '+bankNames[bank]+' observations…';
    const file=bank+'-cross-asset-events';
    const [main,days,intraday,policyFile,newsFile,newsAudit,newsCatalogue]=await Promise.allSettled([data(file),bank==='fed'?data('fed-speech-cross-asset-events'):Promise.resolve(null),bank==='fed'?data('fed-speech-intraday-assets'):Promise.resolve(null),data('stance-cohorts'),data('news-framing'),data('news-coverage-audit'),data('news-catalogue-summary')]);
    if(ticket!==loadToken)return;
    if(main.status!=='fulfilled') {
      $('filters').hidden=false;$('status').textContent='The '+bankNames[bank]+' market observations could not be loaded. Refresh this page to retry.';return;
    }
    let mainData=main.value;
    missingParts=[];speechPartsLoaded=!(mainData.parts?.length);
    if(mainData.parts?.length&&(state.stage==='speech'||preferred?.startsWith('ecb-speech-'))) {
      const chunks=await Promise.allSettled(mainData.parts.map(data));
      if(ticket!==loadToken)return;
      const extra=[];
      for(let i=0;i<chunks.length;i++) {
        const chunk=chunks[i];
        if(chunk.status==='fulfilled'&&Array.isArray(chunk.value.records))extra.push(...chunk.value.records);
        else missingParts.push(mainData.parts[i]);
      }
      mainData={...mainData,records:[...mainData.records,...extra]};speechPartsLoaded=true;
    }
    packages=[[mainData,file]];
    if(days.status==='fulfilled' && days.value)packages.push([days.value,'fed-speech-cross-asset-events']);
    if(intraday.status==='fulfilled' && intraday.value)packages.push([intraday.value,'fed-speech-intraday-assets']);
    cohorts=new Map((policyFile.value?.banks?.find(b=>b.id===bank)?.records||[]).map(e=>[e.date,e]));
    news=new Map();newsAvailable=newsFile.status==='fulfilled';newsMethods=Array.isArray(newsFile.value?.method)?newsFile.value.method:[];
    for(const x of newsFile.value?.records||[])if(x.bank===bank) {if(!news.has(x.date))news.set(x.date,[]);news.get(x.date).push(x);}
    annualNewsCoverage(newsFile.value?.asOf,newsAudit.value,newsCatalogue.value,newsFile.value?.records);
    for(const group of news.values()) group.sort((a,b)=>(a.publishedAt||a.publicationDate||'').localeCompare(b.publishedAt||b.publicationDate||''));
    events=packages.flatMap(([f,key])=>f.records.map(r=>({...r,_package:f,_file:key}))).sort((a,b)=>b.date.localeCompare(a.date)||(b.time||'').localeCompare(a.time||'')||a.id.localeCompare(b.id));
    const stages=new Map();for(const [p] of packages)for(const [key,o] of Object.entries(p.stages||{})) if(events.some(r=>r.stage===key)||(key==='speech' && p.parts?.length)) stages.set(key,o.label||key);
    const found=events.find(r=>r.id===preferred);if(found)state.stage=found.stage;
    requestedMissing=preferred===wanted('event') && !found ? preferred : '';
    state.stage=options($('stage'),[...stages],state.stage);
    $('filters').hidden=false;$('layout').hidden=false;
    syncStage(state.stage,preferred);
  }
  $('bank').onchange=()=>{requestedMissing='';state.leader='';state.year='';state.query='';$('query').value='';state.lens='';$('lens').value='';state.asset='';loadBank($('bank').value,'');};
  $('stage').onchange=()=>{
    requestedMissing='';
    const next=$('stage').value;
    if(next==='speech' && !speechPartsLoaded) {state.stage=next;loadBank(state.bank,chosen?.date);return;}
    syncStage(next,chosen?.date);
  };
  $('leader').onchange=()=>{requestedMissing='';state.leader=$('leader').value;refresh(chosen?.id);};
  $('year').onchange=()=>{requestedMissing='';state.year=$('year').value;refresh(chosen?.id);};
  $('lens').onchange=()=>{requestedMissing='';state.lens=$('lens').value;refresh(chosen?.id);};
  $('query').oninput=()=>{requestedMissing='';state.query=$('query').value;refresh(chosen?.id);};
  $('prev').onclick=()=>{state.page--;index();};
  $('next').onclick=()=>{state.page++;index();};
  for(const key of ['stage','leader','year','asset','query'])if(wanted(key))state[key]=wanted(key);
  if(wanted('speaker') && !state.query)state.query=wanted('speaker');
  if(['news','scored','hawk','dove','wait'].includes(wanted('lens')))state.lens=wanted('lens');
  $('lens').value=state.lens;$('query').value=state.query;
  if(mobile())$('index').open=false;
  const bank=wanted('bank')==='ecb'?'ecb':'fed';
  const def=state.stage==='release'?(bank==='fed'?'2022-11-02':'2023-05-04'):'';
  loadBank(bank,wanted('event')||wanted('date')||def);
})();
