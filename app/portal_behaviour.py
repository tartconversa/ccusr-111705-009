"""本地业务页面交互。"""

def detail_fragment(item):
    return '<button id="pan">平移地图</button><button id="zoom">缩放</button><div id="viewport" data-region="中心区"><button class="marker" data-store="store-01">武康路门店</button></div><script>document.querySelector(\'#pan\').onclick=()=>{document.querySelector(\'#viewport\').dataset.region=\'东区\';document.querySelector(\'.marker\').dataset.store=\'store-02\';document.querySelector(\'.marker\').textContent=\'东区门店\'};document.querySelector(\'#zoom\').onclick=()=>document.querySelector(\'.marker\').hidden=true;</script>'
