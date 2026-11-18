const hint=document.querySelector('.hint');
hint.textContent='Tab 打开背包　Esc 收起背包';
document.addEventListener('keydown',event=>{
  if(event.key!=='Tab' && event.key!=='Escape')return;
  event.preventDefault();
  if(event.key==='Tab')document.body.classList.toggle('inventory-mode');
  else document.body.classList.remove('inventory-mode');
});
