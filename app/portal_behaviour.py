"""本地业务页面交互。"""

def detail_fragment(item):
    return "<button id=\"pan\">平移地图</button><button id=\"zoom\">缩放</button><div id=\"viewport\" data-region=\"中心区\"><button class=\"marker\" data-store=\"store-01\">武康路门店</button></div><output id=\"store-popover\"></output><button id=\"brand\">查看品牌页</button><output id=\"brand-state\"></output><script>let viewport=document.querySelector('#viewport'),marker=document.querySelector('.marker'),popover=document.querySelector('#store-popover'),brand=document.querySelector('#brand-state');document.querySelector('#pan').onclick=()=>{viewport.dataset.region='东区';marker.dataset.store='store-02';marker.textContent='东区门店';popover.textContent='';brand.textContent=''};document.querySelector('#zoom').onclick=()=>{marker.hidden=true;viewport.dataset.complete='false'};marker.onclick=()=>popover.textContent=marker.dataset.store+' / '+(marker.dataset.store==='store-01'?'武康路 10 号':'武康路 12 号');document.querySelector('#brand').onclick=()=>brand.textContent=marker.dataset.store==='store-01'?'营业中':'试营业';</script>"

def source_extension(item):
    return """<output id="map-scope" data-visited="center">中心区已访问</output><output id="brand-address"></output><script>(()=>{
let scope=document.querySelector('#map-scope'),address=document.querySelector('#brand-address'),marker=document.querySelector('.marker'),popover=document.querySelector('#store-popover');
document.querySelector('#pan').addEventListener('click',()=>{scope.dataset.visited='center,east';scope.textContent='中心区、东区已访问';address.textContent='';});
marker.addEventListener('click',()=>{address.textContent=popover.textContent;});
document.querySelector('#brand').addEventListener('click',()=>{address.textContent=popover.textContent?popover.textContent+' / '+document.querySelector('#brand-state').textContent:'标记地址待核对';});
document.querySelector('#zoom').addEventListener('click',()=>{scope.textContent='部分区域未加载';});
})();</script>"""
