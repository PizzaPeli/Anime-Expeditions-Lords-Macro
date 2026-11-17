from test_ui_js import run_js


def test_import_only_offers_categories_present_in_backup(tmp_path):
    out = run_js("""
        const boxes = Object.fromEntries(['settings','tasks','macros','resources'].map(k => ['backup-'+k, {}]));
        const elements = new Proxy(boxes, {get: (o,k) => o[k] || (o[k]={style:{}})});
        global.document = {getElementById: k => elements[k]};
        let backupImportData = null, backupBusy = false;
        const payload = {kind:'anime-expeditions-backup',version:1,sections:{tasks:{},resources:{}}};
        global.pywebview = {api:{is_macro_running:async()=>({running:false}),
            import_tasks_file:async()=>({ok:true,data:payload}),hide_game:async()=>{}}};
        eval(extract('openBackupTransfer'));
        (async()=>{await openBackupTransfer('import');
        console.log(JSON.stringify({settings:boxes['backup-settings'],tasks:boxes['backup-tasks'],
            resources:boxes['backup-resources'],display:elements['backup-modal'].style.display}));})();
    """, tmp_path)
    assert out["settings"] == {"disabled": True, "checked": False}
    assert out["tasks"] == {"disabled": False, "checked": True}
    assert out["resources"] == {"disabled": False, "checked": True}
    assert out["display"] == "flex"


def test_old_export_import_uses_existing_handler_without_second_dialog(tmp_path):
    out = run_js("""
        let backupImportData = null, backupBusy = false;
        let calls = 0, received = null;
        global.pywebview = {api:{is_macro_running:async()=>({running:false}),
            import_tasks_file:async()=>{calls++;return {ok:true,data:{kind:'anime-expeditions-tasks',tasks:[]}};}}};
        async function importTasks(result) {received=result;}
        eval(extract('openBackupTransfer'));
        (async()=>{await openBackupTransfer('import');
        console.log(JSON.stringify({calls,kind:received.data.kind}));})();
    """, tmp_path)
    assert out == {"calls": 1, "kind": "anime-expeditions-tasks"}


def test_export_flushes_current_queue_and_passes_selected_categories(tmp_path):
    out = run_js("""
        let backupImportData = null, backupBusy = false, taskSaveTimer = null;
        const taskCards = [{id:'latest-edit'}];
        const calls=[];
        const elements = new Proxy({}, {get:(o,k)=>o[k]||(o[k]={style:{},value:'merge'})});
        global.document={getElementById:k=>elements[k]};
        function backupSelection(){return ['tasks','resources'];}
        function addLog(){}
        global.pywebview={api:{
            save_tasks:async(tasks)=>{calls.push(['save',tasks]);return {ok:true};},
            create_backup_bundle:async(selected)=>{calls.push(['prepare',selected]);return {ok:true,data:{kind:'backup'}};},
            export_tasks_file:async(data,prefix)=>{calls.push(['write',data,prefix]);return {ok:true};}
        }};
        eval(extract('applyBackupTransfer'));
        (async()=>{await applyBackupTransfer();console.log(JSON.stringify(calls));})();
    """, tmp_path)
    assert out == [["save", [{"id": "latest-edit"}]], ["prepare", ["tasks", "resources"]],
                   ["write", {"kind": "backup"}, "backup"]]
