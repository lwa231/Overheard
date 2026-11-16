/* Skin registry. `scheme` picks the matching light/dark base tokens; `ramp` recolours the heat scale for that skin. */
const SKINS=[
 {id:'classic',name:'Classic',scheme:'dark'},
 {id:'paper',name:'Paper',scheme:'light',ramp:[[0,[238,226,200]],[.3,[236,196,140]],[.6,[230,140,80]],[.85,[217,56,30]],[1,[120,20,10]]]},
 {id:'terminal',name:'Terminal',scheme:'dark',ramp:[[0,[10,50,28]],[.4,[20,140,70]],[.75,[57,255,136]],[1,[220,255,235]]]},
 {id:'brutal',name:'Brutal',scheme:'light',ramp:[[0,[255,240,150]],[.35,[255,160,60]],[.7,[255,62,138]],[1,[10,10,10]]]},
 {id:'signal',name:'Signal',scheme:'dark',ramp:[[0,[40,40,44]],[.4,[120,120,128]],[.75,[255,90,90]],[1,[255,255,255]]]},
 {id:'aurora',name:'Aurora',scheme:'dark',ramp:[[0,[80,60,200]],[.35,[40,190,230]],[.65,[130,250,200]],[.85,[255,180,220]],[1,[255,255,255]]]},
 {id:'mint',name:'Mint',scheme:'light',ramp:[[0,[200,235,222]],[.4,[90,200,160]],[.75,[15,157,117]],[1,[6,60,45]]]},
 {id:'amber',name:'Amber',scheme:'dark',ramp:[[0,[40,28,0]],[.4,[150,100,0]],[.75,[255,176,0]],[1,[255,240,190]]]},
 {id:'violet',name:'Violet',scheme:'dark'},
 {id:'lime',name:'Lime',scheme:'dark',ramp:[[0,[40,50,20]],[.4,[110,160,30]],[.75,[200,255,46]],[1,[250,255,220]]]},
 {id:'sand',name:'Sand',scheme:'light',ramp:[[0,[226,214,190]],[.4,[190,160,110]],[.75,[47,93,80]],[1,[18,45,38]]]},
 {id:'ice',name:'Ice',scheme:'light',ramp:[[0,[210,225,250]],[.4,[110,160,245]],[.75,[37,99,235]],[1,[10,30,100]]]},
 {id:'dots',name:'Dots',scheme:'dark',ramp:[[0,[40,40,42]],[.5,[170,170,175]],[.8,[255,255,255]],[1,[255,59,48]]]},
 {id:'panel',name:'Panel',scheme:'light',ramp:[[0,[225,225,220]],[.4,[255,190,130]],[.75,[255,102,0]],[1,[20,20,20]]]},
 {id:'linear',name:'Linear',scheme:'dark',ramp:[[0,[40,38,70]],[.4,[90,70,200]],[.75,[124,92,255]],[1,[225,215,255]]]},
 {id:'crt',name:'CRT',scheme:'dark',ramp:[[0,[8,40,18]],[.45,[20,150,60]],[.8,[51,255,102]],[1,[255,176,0]]]},
 {id:'rings',name:'Rings',scheme:'dark',ramp:[[0,[40,40,46]],[.35,[0,200,220]],[.65,[166,255,0]],[.85,[255,214,10]],[1,[250,17,79]]]},
 {id:'stripe',name:'Stripe',scheme:'light',ramp:[[0,[225,230,255]],[.4,[140,130,255]],[.75,[99,91,255]],[1,[10,37,64]]]},
 {id:'slate',name:'Slate',scheme:'dark',ramp:[[0,[29,49,51]],[0.4,[57,129,120]],[0.75,[94,234,212]],[1,[223,251,246]]]},
 {id:'ember',name:'Ember',scheme:'dark',ramp:[[0,[46,21,12]],[0.4,[136,58,30]],[0.75,[255,107,53]],[1,[255,225,215]]]},
 {id:'oxide',name:'Oxide',scheme:'dark',ramp:[[0,[39,32,27]],[0.4,[119,71,56]],[0.75,[224,122,95]],[1,[249,228,223]]]},
 {id:'plum',name:'Plum',scheme:'dark',ramp:[[0,[52,27,46]],[0.4,[135,64,105]],[0.75,[244,114,182]],[1,[253,227,240]]]},
 {id:'cobalt',name:'Cobalt',scheme:'dark',ramp:[[0,[14,25,58]],[0.4,[41,68,143]],[0.75,[77,124,255]],[1,[219,229,255]]]},
 {id:'graphite',name:'Graphite',scheme:'dark',ramp:[[0,[39,39,39]],[0.4,[132,132,132]],[0.75,[255,255,255]],[1,[255,255,255]]]},
 {id:'moss',name:'Moss',scheme:'dark',ramp:[[0,[31,43,15]],[0.4,[88,124,32]],[0.75,[163,230,53]],[1,[237,250,215]]]},
 {id:'dusk',name:'Dusk',scheme:'dark',ramp:[[0,[53,39,38]],[0.4,[138,104,37]],[0.75,[251,191,36]],[1,[254,242,211]]]},
 {id:'neon',name:'Neon',scheme:'dark',ramp:[[0,[37,9,39]],[0.4,[131,24,114]],[0.75,[255,43,214]],[1,[255,213,247]]]},
 {id:'ocean',name:'Ocean',scheme:'dark',ramp:[[0,[10,40,54]],[0.4,[30,104,138]],[0.75,[56,189,248]],[1,[215,242,254]]]},
 {id:'rose',name:'Rose',scheme:'light',ramp:[[0,[239,206,212]],[0.4,[226,151,182]],[0.75,[190,24,93]],[1,[48,6,23]]]},
 {id:'citrus',name:'Citrus',scheme:'light',ramp:[[0,[252,225,190]],[0.4,[246,180,146]],[0.75,[234,88,12]],[1,[58,22,3]]]},
 {id:'sky',name:'Sky',scheme:'light',ramp:[[0,[199,228,245]],[0.4,[141,200,230]],[0.75,[2,132,199]],[1,[0,33,50]]]},
 {id:'lavender',name:'Lavender',scheme:'light',ramp:[[0,[223,211,247]],[0.4,[196,166,247]],[0.75,[124,58,237]],[1,[31,14,59]]]},
 {id:'ledger',name:'Ledger',scheme:'light',ramp:[[0,[216,220,228]],[0.4,[153,175,237]],[0.75,[29,78,216]],[1,[7,20,54]]]},
 {id:'blueprint',name:'Blueprint',scheme:'dark',ramp:[[0,[39,68,113]],[0.4,[132,148,174]],[0.75,[255,255,255]],[1,[255,255,255]]]},
 {id:'chalk',name:'Chalk',scheme:'dark',ramp:[[0,[55,67,61]],[0.4,[137,144,140]],[0.75,[245,245,244]],[1,[253,253,253]]]},
 {id:'coral',name:'Coral',scheme:'light',ramp:[[0,[254,212,209]],[0.4,[250,169,183]],[0.75,[244,63,94]],[1,[61,16,24]]]},
 {id:'mono-light',name:'Mono Light',scheme:'light',ramp:[[0,[211,211,211]],[0.4,[148,148,148]],[0.75,[17,17,17]],[1,[4,4,4]]]},
 {id:'olive',name:'Olive',scheme:'light',ramp:[[0,[211,214,189]],[0.4,[175,181,152]],[0.75,[77,91,27]],[1,[19,23,7]]]},
 {id:'sunrise',name:'Sunrise',scheme:'light',ramp:[[0,[251,210,197]],[0.4,[242,153,173]],[0.75,[225,29,72]],[1,[56,7,18]]]},
 {id:'steel',name:'Steel',scheme:'dark',ramp:[[0,[32,37,43]],[0.4,[82,92,104]],[0.75,[148,163,184]],[1,[234,237,241]]]},
 {id:'toxic',name:'Toxic',scheme:'dark',ramp:[[0,[23,38,4]],[0.4,[82,132,2]],[0.75,[158,255,0]],[1,[236,255,204]]]},
 {id:'copper',name:'Copper',scheme:'dark',ramp:[[0,[44,29,19]],[0.4,[118,78,48]],[0.75,[217,142,87]],[1,[247,232,221]]]},
 {id:'glacier',name:'Glacier',scheme:'light',ramp:[[0,[207,228,232]],[0.4,[147,192,205]],[0.75,[14,116,144]],[1,[4,29,36]]]},
 {id:'candy',name:'Candy',scheme:'light',ramp:[[0,[223,225,239]],[0.4,[143,222,236]],[0.75,[6,182,212]],[1,[2,46,53]]]},
 {id:'noir',name:'Noir',scheme:'dark',ramp:[[0,[27,23,15]],[0.4,[114,96,62]],[0.75,[229,192,123]],[1,[250,242,229]]]},
 {id:'pixel',name:'Pixel',scheme:'dark',ramp:[[0,[44,38,31]],[0.4,[135,110,18]],[0.75,[255,204,0]],[1,[255,245,204]]]},
 {id:'zen',name:'Zen',scheme:'light',ramp:[[0,[235,222,209]],[0.4,[221,178,144]],[0.75,[180,83,9]],[1,[45,21,2]]]},
 {id:'aero',name:'Aero',scheme:'light',ramp:[[0,[183,218,235]],[0.4,[142,188,213]],[0.75,[3,105,161]],[1,[1,26,40]]]}
];
window.SKIN_RAMP=null;
function applySkin(id){
  const s=SKINS.find(x=>x.id===id)||SKINS[0],d=document.documentElement;
  d.dataset.skin=s.id;d.dataset.theme=s.id==='classic'?(localStorage.getItem('overheard.theme')||'dark'):s.scheme;
  window.SKIN_RAMP=s.ramp||null;
  try{localStorage.setItem('overheard.skin',s.id)}catch(e){}
  return s;
}
(function(){let id='classic';try{id=new URLSearchParams(location.search).get('skin')||localStorage.getItem('overheard.skin')||'classic'}catch(e){}applySkin(id)})();
