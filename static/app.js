const $ = id => document.getElementById(id);
const localDate = new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
$('date').value = localDate; $('date').min=localDate; const endDate=new Date(localDate+'T00:00:00+08:00');endDate.setDate(endDate.getDate()+4);$('date').max=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(endDate);
const payload = () => ({city:$('city').value.trim(),date:$('date').value,period:$('period').value,activity:$('activity').value,duration_hours:Number($('duration').value),refresh:$('refresh').checked});
async function post(path, body) {
  const response = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json(); return {response,data};
}
async function parse(method) {
  $('parse-status').textContent = '正在解析…'; const buttons=[$('parse-auto'),$('parse-rule'),$('parse-model')];const disabled=buttons.map(x=>x.disabled);buttons.forEach(x=>x.disabled=true);
  try { const {response,data} = await post('/api/parse',{text:$('sentence').value,method});
    if (!response.ok) throw Error(data.error);
    for (const [id,key] of [['city','city'],['date','date'],['period','period'],['activity','activity']]) $(id).value=data[key];
    $('parse-status').textContent = `${data.method==='model'?'AI':'规则'}解析完成，请核对字段后查询。`;
  } catch(e) {$('parse-status').textContent=e.message;} finally {buttons.forEach((x,i)=>x.disabled=disabled[i]);}
}
$('parse-auto').onclick=()=>parse('auto'); $('sentence').onkeydown=e=>{if(e.key==='Enter'&&!$('parse-auto').disabled)parse('auto');}; $('parse-rule').onclick=()=>parse('rule'); $('parse-model').onclick=()=>parse('model');
$('search').onclick=()=>search();
async function search(selected_city=null) {
  if(!payload().city||!payload().date){$('status').textContent='请填写城市和日期。';return;} $('search').disabled=true;$('status').textContent='正在查询…'; $('city-choice').hidden=true; $('results').hidden=true;
  try { const {response,data}=await post('/api/forecast',{...payload(),selected_city});
    if(response.status===409 && data.needs_selection){
      const box=$('city-choice');box.replaceChildren();
      const label=document.createElement('strong');label.textContent='请选择准确的城市：';box.append(label);
      for(const city of data.candidates){const button=document.createElement('button');
        button.textContent=[city.name,city.admin1,city.country].filter(Boolean).join(' · ');
        button.onclick=()=>search(city.id);box.append(button);}box.hidden=false;
      $('status').textContent='找到多个候选地点。';return;
    }
    if(!response.ok) throw Error(data.error||'查询失败');
    render(data);$('status').textContent='查询完成。';loadHistory();
  } catch(e){$('status').textContent=e.message;} finally {$('search').disabled=false;}
}
function render(data){
  $('results').hidden=false;
  $('meta').textContent=`${({snapshot:'历史快照 · ',cache:'15分钟内缓存 · ',stale:'接口暂不可用，显示历史预测 · ',live:'最新获取 · '})[data.source_mode]||(data.snapshot?'历史快照 · ':'')}${data.city.name} · ${data.city.admin1||''} · ${data.city.timezone} · 获取时间 ${new Date(data.fetched_at).toLocaleString('zh-CN')} · 数据来源：Open-Meteo`;
  for(const kind of ['csv','json'])$('export-'+kind).href=`/api/history/${data.query_id}/export.${kind}`; const best=data.best_hour;$('best-hour').textContent=best?`相对优选小时：${best.time.slice(11,16)} · ${best.level}（${best.method}）`:'当前时段没有完整指标，请选择其他时段。';
  const windowResult = data.activity_window;
  if (windowResult) {
    const label = data.query.duration_hours + ' 小时活动';
    const details = windowResult.start
      ? `${windowResult.start.replace('T',' ')} 至 ${windowResult.end.replace('T',' ')} · ${windowResult.level}。最高降水概率 ${windowResult.max_rain}%，最高 European AQI ${windowResult.max_aqi}。`
      : windowResult.message;
    $('best-hour').textContent = label + ' · ' + details + windowResult.reasons.join('；');
  }
  const counts={};for(const row of data.rows)counts[row.advice.level]=(counts[row.advice.level]||0)+1;
  $('summary').textContent=`共 ${data.rows.length} 个小时；较适合 ${counts['较适合']||0}，需留意 ${counts['需留意']||0}，暂不推荐 ${counts['暂不推荐']||0}，数据不完整 ${counts['数据不完整']||0}。`;
  const tbody=$('rows');tbody.replaceChildren();
  for(const row of data.rows){const tr=document.createElement('tr');
    for(const key of ['time','temperature_2m','precipitation_probability','wind_speed_10m','pm2_5','european_aqi']){
      const td=document.createElement('td');td.textContent=key==='time'?row.time.replace('T',' '):(row[key]??'—');tr.append(td);}
    const td=document.createElement('td');const badge=document.createElement('span');badge.className='badge '+(row.advice.level==='暂不推荐'?'bad':row.advice.level==='需留意'?'warn':'');badge.textContent=row.advice.level;td.append(badge);
    const reason=document.createElement('div');reason.textContent=row.advice.reasons.join('；');td.append(reason);tr.append(td);tbody.append(tr);}
  draw(data.rows);
}
function draw(rows){const canvas=$('chart'),ctx=canvas.getContext('2d');const w=canvas.width,h=canvas.height;
  ctx.clearRect(0,0,w,h);ctx.fillStyle='#fff';ctx.fillRect(0,0,w,h);
  const series=[{key:'temperature_2m',label:'气温 °C',color:'#147d87'},{key:'pm2_5',label:'PM2.5 µg/m³',color:'#d46a32'}];
  series.forEach((s,index)=>{const values=rows.map(r=>r[s.key]).filter(v=>Number.isFinite(v));if(!values.length)return;
    const min=Math.min(...values),max=Math.max(...values),spread=max-min||1;const top=25+index*115;
    ctx.fillStyle=s.color;ctx.font='15px sans-serif';ctx.fillText(`${s.label}  ${min}–${max}`,20,top);
    ctx.strokeStyle=s.color;ctx.lineWidth=3;ctx.beginPath();let started=false;
    rows.forEach((r,i)=>{const value=r[s.key];if(!Number.isFinite(value)){started=false;return;}
      const x=30+i*(w-60)/Math.max(rows.length-1,1),y=top+78-(value-min)/spread*55;
      if(started)ctx.lineTo(x,y);else ctx.moveTo(x,y);started=true;});ctx.stroke();});
  ctx.fillStyle='#607380';ctx.font='12px sans-serif';rows.forEach((r,i)=>{if(i%Math.max(1,Math.ceil(rows.length/9))===0)ctx.fillText(r.time.slice(11,16),30+i*(w-60)/Math.max(rows.length-1,1)-12,h-8);});
}

async function loadHistory(){
  try {const response=await fetch('/api/history');if(!response.ok)throw Error('无法加载历史记录');
    const data=await response.json();const select=$('history');select.replaceChildren();
    for(const item of data.items){const option=document.createElement('option');option.value=item.id;
      option.textContent=`${item.city} · ${item.query.date} ${item.query.period} · ${item.query.activity} ${item.query.duration_hours || 1} 小时 · 采集于 ${new Date(item.fetched_at).toLocaleString('zh-CN')}`;select.append(option);}
    $('replay').disabled=!data.items.length;
  }catch(e){$('status').textContent=e.message;}
}
$('refresh-history').onclick=loadHistory;
$('replay').onclick=async()=>{try{const response=await fetch(`/api/history/${$('history').value}`);const data=await response.json();if(!response.ok)throw Error(data.error);render(data);$('status').textContent='已显示该次查询记录。';}catch(e){$('status').textContent=e.message;}};
loadHistory();
