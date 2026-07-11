import { Button, Form, Input, InputNumber, Modal, Select, Switch, Tag } from 'antd';
import { Cable, FolderPlus, Pencil, PlugZap, Save, Server, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';

import {
  createImportSource,
  deleteImportSource,
  getImportSettings,
  testImportSource,
  updateImportOptions,
  updateImportSource,
} from '../../services/api';
import { useWorkspaceStore } from '../../stores/useWorkspaceStore';
import type { ImportSettings, ImportSourceProfile, ImportSourceWrite } from '../../types/imports';

const emptySource: ImportSourceWrite = {
  name: '',
  kind: 'local',
  root_path: '',
  server: '',
  share: '',
  base_path: '',
  username: '',
  domain: '',
  port: 445,
  encrypt: true,
  enabled: true,
  password: '',
};

export function ImportSourceSettings() {
  const [settings, setSettings] = useState<ImportSettings | null>(null);
  const [editing, setEditing] = useState<ImportSourceProfile | null | undefined>(undefined);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<ImportSourceWrite>();
  const kind = Form.useWatch('kind', form);
  const showNotice = useWorkspaceStore((state) => state.showNotice);

  const load = () =>
    getImportSettings()
      .then(setSettings)
      .catch((error) =>
        showNotice({
          tone: 'warning',
          title: '数据源加载失败',
          detail: error instanceof Error ? error.message : '未知错误',
        }),
      );

  useEffect(() => {
    void load();
  }, []);

  const openEditor = (source?: ImportSourceProfile) => {
    setEditing(source ?? null);
    form.setFieldsValue(
      source
        ? {
            ...source,
            password: '',
          }
        : emptySource,
    );
  };

  const saveSource = async () => {
    const value = await form.validateFields();
    setSaving(true);
    try {
      if (editing) await updateImportSource(editing.id, value);
      else await createImportSource(value);
      setEditing(undefined);
      await load();
      showNotice({ tone: 'success', title: '数据源已保存', detail: value.name });
    } catch (error) {
      showNotice({
        tone: 'warning',
        title: '数据源保存失败',
        detail: error instanceof Error ? error.message : '未知错误',
      });
    } finally {
      setSaving(false);
    }
  };

  const testSource = async (source: ImportSourceProfile) => {
    try {
      const result = await testImportSource(source.id);
      showNotice({ tone: 'success', title: '连接测试通过', detail: result.message });
    } catch (error) {
      showNotice({
        tone: 'warning',
        title: '连接测试失败',
        detail: error instanceof Error ? error.message : '未知错误',
      });
    }
  };

  const removeSource = async (source: ImportSourceProfile) => {
    await deleteImportSource(source.id);
    await load();
    showNotice({ tone: 'info', title: '数据源已删除', detail: source.name });
  };

  return (
    <div className="import-source-settings">
      <div className="section-title settings-section-actions">
        <span className="section-title-label"><Server size={16} />导入与数据源</span>
        <Button size="small" icon={<FolderPlus size={14} />} onClick={() => openEditor()}>
          新增
        </Button>
      </div>

      <div className="import-options-row">
        <Input
          value={settings?.cache_path ?? ''}
          onChange={(event) =>
            setSettings((current) => current && { ...current, cache_path: event.target.value })
          }
          placeholder="缓存目录"
          aria-label="导入缓存目录"
        />
        <InputNumber
          min={100}
          max={20000}
          step={100}
          value={settings?.batch_size}
          onChange={(value) =>
            setSettings((current) => current && { ...current, batch_size: value ?? 2000 })
          }
          aria-label="每批要素数"
        />
        <Button
          icon={<Save size={14} />}
          disabled={!settings}
          onClick={() =>
            settings &&
            void updateImportOptions(settings.cache_path, settings.batch_size).then(setSettings)
          }
        >
          保存
        </Button>
      </div>

      <div className="import-source-list">
        {settings?.sources.map((source) => (
          <div className="import-source-row" key={source.id}>
            <span className="import-source-main">
              <strong>{source.name}</strong>
              <span>
                {source.kind === 'smb'
                  ? `\\\\${source.server}\\${source.share}\\${source.base_path}`
                  : source.root_path}
              </span>
            </span>
            <Tag>{source.kind === 'smb' ? 'SMB' : '本地'}</Tag>
            {source.kind === 'smb' && (
              <Tag>{source.credential_configured ? '凭据已配置' : '缺少凭据'}</Tag>
            )}
            <Button size="small" icon={<PlugZap size={14} />} onClick={() => void testSource(source)}>
              测试
            </Button>
            <Button size="small" icon={<Pencil size={14} />} onClick={() => openEditor(source)} aria-label={`编辑 ${source.name}`} />
            <Button danger size="small" icon={<Trash2 size={14} />} onClick={() => void removeSource(source)} aria-label={`删除 ${source.name}`} />
          </div>
        ))}
        {settings?.sources.length === 0 && <p className="panel-empty">尚未配置本地或 SMB 数据源。</p>}
      </div>

      <Modal
        open={editing !== undefined}
        title={editing ? '编辑数据源' : '新增数据源'}
        onCancel={() => setEditing(undefined)}
        onOk={() => void saveSource()}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={form} layout="vertical" initialValues={emptySource}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入数据源名称' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="kind" label="类型" rules={[{ required: true }]}>
            <Select options={[{ value: 'local', label: '本地目录' }, { value: 'smb', label: 'SMB 共享' }]} />
          </Form.Item>
          {kind === 'local' ? (
            <Form.Item name="root_path" label="根目录" rules={[{ required: true, message: '请输入本地目录' }]}>
              <Input placeholder="D:\\GIS\\source" />
            </Form.Item>
          ) : (
            <>
              <div className="settings-form-grid">
                <Form.Item name="server" label="服务器" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="share" label="共享名" rules={[{ required: true }]}><Input /></Form.Item>
                <Form.Item name="base_path" label="共享内目录"><Input /></Form.Item>
                <Form.Item name="port" label="端口"><InputNumber min={1} max={65535} /></Form.Item>
                <Form.Item name="domain" label="域"><Input /></Form.Item>
                <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input /></Form.Item>
              </div>
              <Form.Item name="password" label="密码">
                <Input.Password placeholder={editing?.credential_configured ? '留空则保留系统凭据' : '保存到 Windows 凭据库'} />
              </Form.Item>
              <Form.Item name="encrypt" label="SMB3 加密" valuePropName="checked"><Switch /></Form.Item>
            </>
          )}
          <Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item>
        </Form>
        <div className="settings-status"><Cable size={15} /><span>密码只保存到 Windows Credential Manager，不写入 YAML。</span></div>
      </Modal>
    </div>
  );
}
