// Study Sentinel - Interactive Knowledge Graph Explorer (Vis.js)

let network = null;

function initGraphViewer(containerId, graphData) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const nodes = new vis.DataSet((graphData.nodes || []).map(n => {
    let color = "#818cf8"; // default subject
    let shape = "dot";
    let size = 18;

    if (n.node_type === "Subject") {
      color = "#818cf8";
      size = 24;
    } else if (n.node_type === "Site") {
      color = "#38bdf8";
      size = 28;
      shape = "square";
    } else if (n.node_type === "AdverseEvent") {
      color = "#f87171";
      size = 20;
      shape = "diamond";
    } else if (n.node_type === "LabResult") {
      color = "#fbbf24";
      size = 16;
    } else if (n.node_type === "Medication") {
      color = "#a78bfa";
      size = 18;
      shape = "triangle";
    } else if (n.node_type === "Dose" || n.node_type === "Visit") {
      color = "#34d399";
      size = 16;
    }

    return {
      id: n.id,
      label: n.label || n.id,
      color: { background: color, border: "#ffffff", highlight: { background: "#ec4899", border: "#ffffff" } },
      shape: shape,
      size: size,
      font: { color: "#f3f4f6", size: 12, face: "Inter" },
      title: `${n.node_type || 'Node'}: ${n.label || n.id}`
    };
  }));

  const edges = new vis.DataSet((graphData.edges || []).map(e => ({
    from: e.from,
    to: e.to,
    label: e.label,
    color: { color: "rgba(255, 255, 255, 0.2)", highlight: "#6366f1" },
    font: { color: "#9ca3af", size: 10, align: "middle" },
    arrows: "to"
  })));

  const data = { nodes: nodes, edges: edges };
  const options = {
    physics: {
      barnesHut: {
        gravitationalConstant: -3500,
        springLength: 100,
        springConstant: 0.04
      },
      stabilization: { iterations: 120 }
    },
    interaction: {
      hover: true,
      tooltipDelay: 150,
      zoomView: true
    }
  };

  if (network) {
    network.destroy();
  }
  network = new vis.Network(container, data, options);

  // Click interaction: highlight and log
  network.on("click", (params) => {
    if (params.nodes && params.nodes.length > 0) {
      const selectedId = params.nodes[0];
      console.log("Selected graph node:", selectedId);
    }
  });
}

window.initGraphViewer = initGraphViewer;
