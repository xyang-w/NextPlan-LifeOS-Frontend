(() => {
  function currentActionInfo(p) {
    const milestones = Array.isArray(p?.milestones) ? p.milestones : [];
    const active = milestones.filter(m => m.status === 'active');
    const planned = milestones.filter(m => m.status === 'planned');

    if (p?.status === 'waiting') {
      return {
        label: '等待中',
        text: p.next_action || '等待外部事项推进'
      };
    }

    if (p?.status === 'completed' || p?.status === 'done') {
      return {
        label: '已完成',
        text: '当前项目已完成'
      };
    }

    if (p?.status === 'planned') {
      return {
        label: '尚未开始',
        text: p.next_action || planned[0]?.name || '等待开始'
      };
    }

    if (active.length) {
      return {
        label: '现在要做',
        text: active.map(m => m.name).join(' · ')
      };
    }

    return {
      label: '现在要做',
      text: p?.next_action || planned[0]?.name || '尚未设置当前动作'
    };
  }

  function installPatch() {
    if (typeof projectCard !== 'function' || typeof renderProjects !== 'function') {
      setTimeout(installPatch, 120);
      return;
    }
    if (window.__NEXTPLAN_CURRENT_ACTION_PATCH__) return;
    window.__NEXTPLAN_CURRENT_ACTION_PATCH__ = true;

    projectCard = function projectCardCurrentAction(p) {
      const pc = projectPct(p);
      const [bg, fg] = colorForCategory(p.category);
      const action = currentActionInfo(p);
      return `<article class="card project-card"><div class="pc-top"><div class="pc-icon" style="background:${bg};color:${fg}">${iconForCategory(p.category)}</div><div class="pc-text"><div class="pc-title">${esc(p.name)}</div><div class="pc-sub">${esc(p.category)} · ${priorityLabel(p.priority)} · ${statusLabel(p.status)}</div></div><div class="pc-pct">${pc}%</div></div><div class="mini-progress"><span style="width:${pc}%"></span></div><div class="pc-next"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="4" width="14" height="16" rx="2"/><path d="M8 2v4m8-4v4M8 10h8"/></svg><div><b>${esc(action.label)}</b>${esc(action.text)}</div></div></article>`;
    };

    renderProjects = function renderProjectsCurrentAction() {
      const area = $('projectAreaFilter').value;
      const status = $('projectStatusFilter').value;
      const ps = (state.projects || []).filter(p => (area === '全部' || p.category === area) && (status === '全部' || p.status === status));
      $('projectList').innerHTML = ps.length ? ps.map(p => {
        const action = currentActionInfo(p);
        return `<div class="list-row"><span class="status-dot ${statusClass(p.status)}"></span><div class="list-main"><div class="list-title">${esc(p.name)}</div><div class="list-sub"><b style="color:var(--text);font-weight:630">${esc(action.label)}：</b>${esc(action.text)}</div><div class="milestone-tags">${(p.milestones || []).map(m => `<span class="priority">${statusLabel(m.status)} · ${esc(m.name)}</span>`).join('')}</div></div><div class="list-meta"><b style="color:var(--text);font-size:16px">${projectPct(p)}%</b><br>${esc(p.category)} · ${priorityLabel(p.priority)}</div></div>`;
      }).join('') : `<div class="empty-state"><b>没有符合条件的项目</b>换一个筛选条件即可。</div>`;
    };

    document.querySelectorAll('.section-head p').forEach(el => {
      if (el.textContent.includes('一眼看到进度与下一步')) el.textContent = '当前所有主要项目，一眼看到进度与当前动作。';
    });
    document.querySelectorAll('#view-projects .view-title p').forEach(el => {
      if (el.textContent.includes('长期目标、状态、里程碑与下一步')) el.textContent = '长期目标、状态、里程碑与当前动作。';
    });

    try { renderHome(); } catch (_) {}
    try { renderProjects(); } catch (_) {}
  }

  installPatch();
})();
