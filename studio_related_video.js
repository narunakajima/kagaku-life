// YouTube Studio のShorts編集画面で「関連動画」に本編を設定するページ内スクリプト
// （/kl-upload と /sc-upload の STEP 3.5 で使う。2026-10-02、SCの86本で実際に動作確認済み）
//
// 使い方（Claude in Chrome の javascript_tool）:
//   1. このファイルの内容を、Studio のページの localStorage に保存する（最初の1回だけ）:
//        localStorage.setItem('rel_fn', `<このファイルの「関数本体」部分（return (async()=>{ ... })() ）>`)
//   2. Shorts の編集画面（studio.youtube.com/video/{SHORTS_ID}/edit）を開いて3秒待ち、次を実行する:
//        await (new Function('KW','FORCE',localStorage.getItem('rel_fn')))("検索語", false)
//      KW   = *_related_targets.py が出した検索語（他のエピソードのタイトルに含まれない先頭部分）
//      FORCE = true なら、すでに設定済みでも上書きする（取り違えの修正用）。通常は false
//   3. 返ってくるJSON: { id, kid, before, label, rel, saved }
//        - skip:'already'  すでに設定済み（before が現在の本編タイトル。期待する本編か確認する）
//        - err:'no-option' 検索語に合う本編が見つからない（その回はスキップして報告）
//        - saved:true      保存ボタンが無効に戻った（保存済み）。念のため読み込み直して確認する
//   4. 最後にlocalStorageを片付ける: localStorage.removeItem('rel_fn')
//
// 座標クリックはウィンドウサイズが操作ごとに変わるため使わない（2026-10-02に失敗した）。
// 「子ども向けか」は未選択のときだけ「いいえ」を選ぶ（選択済みの値は書き換えない）。
//
// ↓ 関数本体（localStorage に保存する文字列。KW・FORCE を引数に取る）
return (async()=>{
  const sl=ms=>new Promise(r=>setTimeout(r,ms));
  function deep(root,sel,out=[]){root.querySelectorAll(sel).forEach(e=>out.push(e));root.querySelectorAll('*').forEach(e=>{if(e.shadowRoot)deep(e.shadowRoot,sel,out)});return out}
  async function until(f,n){for(let i=0;i<n;i++){const v=f();if(v)return v;await sl(300)}return null}
  const id=location.pathname.split('/')[2];
  const trig=await until(()=>deep(document,'ytcp-text-dropdown-trigger').find(e=>(e.innerText||'').trim().startsWith('関連動画')),40);
  if(!trig)return JSON.stringify({id,err:'no-trigger'});
  const rd=()=>{const m=document.body.innerText.match(/関連動画\s*\n\s*([^\n]+)/);return m?m[1].trim():null};
  const before=rd();
  if(before&&before!=='なし'&&!FORCE)return JSON.stringify({id,skip:'already',before});
  // 「子ども向けか」: 未選択のときだけ「いいえ」を選ぶ
  const rs=deep(document,'tp-yt-paper-radio-button').filter(e=>/子ども向け/.test(e.innerText)&&e.innerText.length<80);
  let kid='already';
  if(!rs.some(e=>e.getAttribute('aria-checked')==='true')){
    const no=rs.find(e=>e.innerText.includes('いいえ'));
    if(no){no.click();kid='set-no';await sl(500)}else kid='radio-not-found';
  }
  trig.click();
  const inp=await until(()=>deep(document,'input').find(i=>i.placeholder&&i.placeholder.includes('自分の動画')),20);
  if(!inp)return JSON.stringify({id,err:'no-dialog',kid});
  inp.focus();inp.value=KW;inp.dispatchEvent(new Event('input',{bubbles:true,composed:true}));
  await sl(1800);
  // 本編（#Shorts が付かない方）で、検索語を含む選択肢
  const opt=await until(()=>deep(document,'[role=option]').find(o=>{const l=o.getAttribute('aria-label')||'';return l.includes(KW)&&!l.includes('#Shorts')}),20);
  const n=deep(document,'[role=option]').length;
  if(!opt)return JSON.stringify({id,err:'no-option',n,kid,before});
  const label=opt.getAttribute('aria-label');
  opt.click();await sl(1200);
  const save=deep(document,'ytcp-button').find(b=>(b.innerText||'').trim()==='保存');
  if(!save)return JSON.stringify({id,err:'no-save',kid});
  save.click();await sl(3500);
  return JSON.stringify({id,kid,n,before,label,rel:rd(),saved:!!(save.hasAttribute('disabled')||save.getAttribute('aria-disabled')==='true')});
})()
