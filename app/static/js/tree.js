document.addEventListener('DOMContentLoaded', function(){
  const treeNodes = document.querySelectorAll('.tree-node');
  if(!treeNodes.length){
    return;
  }

  treeNodes.forEach(function(node){
    const children = node.querySelector(':scope > .tree-children');
    const item = node.querySelector(':scope > .tree-item');
    const caret = node.querySelector(':scope > .tree-item .tree-caret');

    if(!children){
      if(caret){
        caret.classList.add('empty');
      }
      return;
    }

    if(!node.classList.contains('expanded')){
      node.classList.add('collapsed');
    }

    if(item){
      item.addEventListener('click', function(){
        node.classList.toggle('expanded');
        node.classList.toggle('collapsed');
      });
    }
  });
});
