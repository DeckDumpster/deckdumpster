(function () {
  document.addEventListener('DOMContentLoaded', async function () {
    const header = document.querySelector('.site-header') ||
      document.querySelector('header') ||
      document.querySelector('.page-header');
    if (!header) return;

    let currentUser = null;
    let users = [];

    try {
      const [curRes, usersRes] = await Promise.all([
        fetch('/api/current-user'),
        fetch('/api/users'),
      ]);
      const curData = await curRes.json();
      const usersData = await usersRes.json();
      currentUser = curData.user || null;
      users = usersData.users || [];
    } catch (e) {
      return;
    }

    const container = document.createElement('div');
    container.id = 'user-switcher';
    container.style.cssText =
      'position:relative;display:inline-block;margin-left:auto;font-size:14px;';

    const btn = document.createElement('button');
    btn.id = 'user-switcher-btn';
    btn.textContent = currentUser || 'Select User';
    btn.style.cssText = [
      'background:#1a1a2e',
      'color:#e0e0e0',
      'border:1px solid #333355',
      'border-radius:4px',
      'padding:6px 12px',
      'cursor:pointer',
      'font-size:14px',
      'font-family:inherit',
      'display:flex',
      'align-items:center',
      'gap:6px',
    ].join(';');

    const arrow = document.createElement('span');
    arrow.textContent = '\u25BE';
    arrow.style.cssText = 'font-size:10px;opacity:0.7;';
    btn.appendChild(arrow);

    const menu = document.createElement('div');
    menu.id = 'user-switcher-menu';
    menu.style.cssText = [
      'display:none',
      'position:absolute',
      'right:0',
      'top:100%',
      'margin-top:4px',
      'background:#1a1a2e',
      'border:1px solid #333355',
      'border-radius:4px',
      'min-width:160px',
      'z-index:9999',
      'box-shadow:0 4px 12px rgba(0,0,0,0.5)',
      'max-height:300px',
      'overflow-y:auto',
    ].join(';');

    function itemStyle(active) {
      return [
        'display:block',
        'width:100%',
        'text-align:left',
        'background:' + (active ? '#2a2a4e' : 'transparent'),
        'color:#e0e0e0',
        'border:none',
        'padding:8px 12px',
        'cursor:pointer',
        'font-size:14px',
        'font-family:inherit',
        'white-space:nowrap',
      ].join(';');
    }

    function buildMenu() {
      menu.innerHTML = '';
      users.forEach(function (name) {
        const item = document.createElement('button');
        item.textContent = name;
        item.style.cssText = itemStyle(name === currentUser);
        item.addEventListener('mouseenter', function () {
          item.style.background = '#2a2a4e';
        });
        item.addEventListener('mouseleave', function () {
          item.style.background = name === currentUser ? '#2a2a4e' : 'transparent';
        });
        item.addEventListener('click', function () {
          selectUser(name);
        });
        menu.appendChild(item);
      });

      if (users.length > 0) {
        const sep = document.createElement('div');
        sep.style.cssText = 'border-top:1px solid #333355;margin:4px 0;';
        menu.appendChild(sep);
      }

      const newItem = document.createElement('button');
      newItem.textContent = '+ New User';
      newItem.style.cssText = itemStyle(false);
      newItem.style.color = '#8888cc';
      newItem.addEventListener('mouseenter', function () {
        newItem.style.background = '#2a2a4e';
      });
      newItem.addEventListener('mouseleave', function () {
        newItem.style.background = 'transparent';
      });
      newItem.addEventListener('click', function () {
        menu.style.display = 'none';
        createNewUser();
      });
      menu.appendChild(newItem);
    }

    function sanitizeName(raw) {
      return raw
        .toLowerCase()
        .replace(/[^a-z0-9_-]/g, '')
        .slice(0, 32);
    }

    async function selectUser(name) {
      try {
        await fetch('/api/user/select', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user: name }),
        });
        location.reload();
      } catch (e) {
        // let it crash visibly in the console
        throw e;
      }
    }

    async function createNewUser() {
      const raw = prompt('Enter a new user name:');
      if (!raw) return;
      const name = sanitizeName(raw);
      if (!name) {
        alert('Invalid name. Use only letters, numbers, hyphens, and underscores.');
        return;
      }
      try {
        await fetch('/api/users', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name }),
        });
        await selectUser(name);
      } catch (e) {
        throw e;
      }
    }

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      const visible = menu.style.display !== 'none';
      menu.style.display = visible ? 'none' : 'block';
    });

    document.addEventListener('click', function () {
      menu.style.display = 'none';
    });

    menu.addEventListener('click', function (e) {
      e.stopPropagation();
    });

    buildMenu();
    container.appendChild(btn);
    container.appendChild(menu);
    header.appendChild(container);

    if (!currentUser && users.length > 0) {
      menu.style.display = 'block';
    }
  });
})();
