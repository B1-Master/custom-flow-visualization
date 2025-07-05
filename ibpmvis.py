import re
import json
import argparse
import sys
from collections import defaultdict, deque


def readFlow(file):
    nodes = {}

    for node in file['nodes']:
        # Skip exception nodes
        if node.get('node_type__alias') == 'exception':
            continue
        output = {}
        # Collect output fields
        for field in node['data'].get('output', []):
            output[field['alias']] = {'formula': field.get('formula', '')}
        # Collect inoutput fields
        for field in node['data'].get('inoutput', []):
            output[field['alias']] = {'formula': field.get('alias', '')}
        # Collect selected fields
        for field in node['data'].get('fields', []):
            if field.get('select'):
                output[field['alias']] = {'formula': field.get('alias', '')}
        nodes[str(node['alias'])] = {
            'name': node.get('name'),
            'alias': node.get('alias'),
            'nodeType': node.get('node_type__alias'),
            'output': output
        }

    allLinks = []
    # Build links based on formulas
    for edge in file['edges']:
        src = str(edge['source'])
        tgt = str(edge['target'])
        sourceFields = nodes[src]['output']
        targetFields = nodes[tgt]['output']
        for tField, tMeta in targetFields.items():
            formula = tMeta.get('formula', '')
            for sField in sourceFields:
                pattern = r'(?<![a-zA-Z0-9_])' + re.escape(
                    sField) + r'(?![a-zA-Z0-9_])'
                if re.search(pattern, formula):
                    # Record link
                    nodes[tgt]['output'][tField]['source'] = {
                        'nodeId': src,
                        'fieldAlias': sField
                    }
                    allLinks.append({
                        'source': {
                            'nodeId': src,
                            'fieldAlias': sField
                        },
                        'target': {
                            'nodeId': tgt,
                            'fieldAlias': tField
                        }
                    })
    return {'nodes': nodes, 'allLinks': allLinks}


def compute_levels(nodes, links):
    children = defaultdict(list)
    indegree = {nid: 0 for nid in nodes}
    for link in links:
        src = link['source']['nodeId']
        tgt = link['target']['nodeId']
        children[src].append(tgt)
        indegree[tgt] = indegree.get(tgt, 0) + 1
    queue = deque([nid for nid, deg in indegree.items() if deg == 0])
    levels = {nid: None for nid in nodes}
    for nid in queue:
        levels[nid] = 0
    while queue:
        nid = queue.popleft()
        for c in children[nid]:
            indegree[c] -= 1
            lvl = levels[nid] + 1
            if levels[c] is None or lvl > levels[c]:
                levels[c] = lvl
            if indegree[c] == 0:
                queue.append(c)
    groups = defaultdict(list)
    for nid, lvl in levels.items():
        groups[lvl].append(nid)
    return [groups[l] for l in sorted(groups)]


def main():
    parser = argparse.ArgumentParser(
        description=
        'Generate an HTML flow diagram from a JSON definition of nodes and edges.'
    )
    parser.add_argument('input_file', help='Path to the input JSON file')
    parser.add_argument('output_file', help='Path to the output HTML file')
    args = parser.parse_args()

    try:
        file = json.load(open(args.input_file, 'r', encoding='utf-8'))
        part = file['flow'][0]
        data = readFlow(file['flow'][0])
    except Exception as e:
        print(f"Failed to load JSON: {e}", file=sys.stderr)
        sys.exit(1)

    nodes = data.get('nodes', {})
    links = data.get('allLinks', [])
    levels = compute_levels(nodes, links)

    payload = {'nodes': nodes, 'links': links, 'levels': levels}
    json_data = json.dumps(payload)

    # HTML template with full-width SVG update
    html_template = """<!DOCTYPE html>
<html>
<head>
  <meta charset=\"utf-8\">
  <title>Flow Visualization</title>
  <style>
    body { margin:0; padding:0; font-family:sans-serif; position:relative; }
    #container { display:grid; grid-auto-flow:column; grid-auto-columns:max-content; grid-gap:80px; padding:20px; align-items:start; }
    .level { display:flex; flex-direction:column; align-items:center; }
    .node { border:1px solid #ccc; border-radius:4px; margin-bottom:40px; min-width:150px; background:#fafafa; }
    .node-header { background:#e0e0e0; padding:8px; font-weight:bold; text-align:center; border-bottom:1px solid #ccc; }
    .fields { list-style:none; padding:0; margin:0; }
    .field { padding:6px 8px; cursor:pointer; position:relative; white-space:nowrap; }
    .field.highlighted { background:#fdd835; }
    .field.selected { background:#ff7043; }
    svg { position:absolute; top:0; left:0; pointer-events:none; }
    path.link { stroke:#888; fill:none; stroke-width:2; marker-end:url(#arrow); }
    path.link.highlighted { stroke:#d32f2f; stroke-width:3; }
  </style>
</head>
<body>
  <div id=\"container\"></div>
  <svg>
    <defs>
      <marker id=\"arrow\" markerWidth=\"10\" markerHeight=\"10\" refX=\"10\" refY=\"5\" orient=\"auto\">
        <path d=\"M0,0 L0,10 L10,5 Z\" fill=\"#888\"/>
      </marker>
    </defs>
  </svg>
  <script id=\"flow-data\" type=\"application/json\">FLOW_JSON</script>
  <script>
    document.addEventListener('DOMContentLoaded', function() {
      var p = JSON.parse(document.getElementById('flow-data').textContent);
      var nodes = p.nodes, links = p.links, levels = p.levels;
      var container = document.getElementById('container');
      var svg = document.querySelector('svg'), ns = 'http://www.w3.org/2000/svg';

      // Render nodes
      levels.forEach(function(level) {
        var lvlDiv = document.createElement('div'); lvlDiv.className = 'level';
        level.forEach(function(nid) {
          var node = nodes[nid];
          var card = document.createElement('div'); card.className = 'node'; card.dataset.node = nid;
          var hdr = document.createElement('div'); hdr.className = 'node-header'; hdr.textContent = node.alias || node.name || nid;
          card.appendChild(hdr);
          var ul = document.createElement('ul'); ul.className = 'fields';
          Object.keys(node.output).forEach(function(fa) {
            var liEl = document.createElement('li');
            liEl.className = 'field'; liEl.dataset.node = nid; liEl.dataset.field = fa;
            liEl.title = node.output[fa].formula || '';
            liEl.textContent = fa;
            ul.appendChild(liEl);
          });
          card.appendChild(ul);
          lvlDiv.appendChild(card);
        });
        container.appendChild(lvlDiv);
      });

      // Build adjacency maps
      var fwd = {}, bwd = {};
      links.forEach(function(l) {
        var sKey = l.source.nodeId + '|' + l.source.fieldAlias;
        var tKey = l.target.nodeId + '|' + l.target.fieldAlias;
        (fwd[sKey] = fwd[sKey] || []).push(tKey);
        (bwd[tKey] = bwd[tKey] || []).push(sKey);
      });

      // Draw links adjusting SVG to full document size
      function drawLinks() {
        // resize SVG
        var docWidth = document.documentElement.scrollWidth;
        var docHeight = document.documentElement.scrollHeight;
        svg.setAttribute('width', docWidth);
        svg.setAttribute('height', docHeight);
        // clear old
        svg.querySelectorAll('path.link').forEach(function(el) { el.remove(); });
        var scrollTop = window.scrollY || window.pageYOffset;
        var scrollLeft = window.scrollX || window.pageXOffset;
        links.forEach(function(lnk) {
          var sEl = document.querySelector(`.field[data-node="${lnk.source.nodeId}"][data-field="${lnk.source.fieldAlias}"]`);
          var tEl = document.querySelector(`.field[data-node="${lnk.target.nodeId}"][data-field="${lnk.target.fieldAlias}"]`);
          if (!sEl || !tEl) return;
          var r1 = sEl.getBoundingClientRect(), r2 = tEl.getBoundingClientRect();
          var x1 = r1.right + scrollLeft;
          var y1 = r1.top + r1.height/2 + scrollTop;
          var x2 = r2.left + scrollLeft;
          var y2 = r2.top + r2.height/2 + scrollTop;
          var d = `M${x1},${y1} C${x1+50},${y1} ${x2-50},${y2} ${x2},${y2}`;
          var path = document.createElementNS(ns, 'path');
          path.classList.add('link');
          path.dataset.src = `${lnk.source.nodeId}|${lnk.source.fieldAlias}`;
          path.dataset.tgt = `${lnk.target.nodeId}|${lnk.target.fieldAlias}`;
          path.setAttribute('d', d);
          svg.appendChild(path);
        });
      }

      function traverse(map, key, vis) {
        if (vis[key]) return; vis[key] = true;
        (map[key] || []).forEach(k => traverse(map, k, vis));
      }

      function highlightField(key) {
        document.querySelectorAll('.field.highlighted, .field.selected').forEach(el => el.classList.remove('highlighted', 'selected'));
        svg.querySelectorAll('path.link.highlighted').forEach(el => el.classList.remove('highlighted'));
        var sel = document.querySelector(`.field[data-node="${key.split('|')[0]}"][data-field="${key.split('|')[1]}"]`);
        if (sel) sel.classList.add('selected');
        var anc = {}, desc = {};
        traverse(bwd, key, anc); traverse(fwd, key, desc);
        var all = {...anc, ...desc}; all[key] = true;
        Object.keys(all).forEach(k => {
          var [nid, fa] = k.split('|');
          var el = document.querySelector(`.field[data-node="${nid}"][data-field="${fa}"]`);
          if (el && !el.classList.contains('selected')) el.classList.add('highlighted');
        });
        svg.querySelectorAll('path.link').forEach(ph => {
          if (all[ph.dataset.src] && all[ph.dataset.tgt]) ph.classList.add('highlighted');
        });
      }

      document.querySelectorAll('.field').forEach(el => {
        el.addEventListener('click', () => highlightField(el.dataset.node + '|' + el.dataset.field));
      });

      // optimized scroll/resize
      var ticking = false;
      function onScrollOrResize() {
        if (!ticking) {
          window.requestAnimationFrame(() => { drawLinks(); ticking = false; });
          ticking = true;
        }
      }
      window.addEventListener('scroll', onScrollOrResize, { passive: true });
      window.addEventListener('resize', onScrollOrResize);

      // initial draw
      drawLinks();
    });
  </script>
</body>
</html>"""

    html = html_template.replace('FLOW_JSON', json_data)
    try:
        with open(args.output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Generated HTML visualization: {args.output_file}")
    except Exception as e:
        print(f"Failed to write HTML file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
