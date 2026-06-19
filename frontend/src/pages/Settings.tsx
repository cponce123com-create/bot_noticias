import { useState, useEffect } from 'react';
import { Save, Settings2, Bot, Globe, Loader2, Send } from 'lucide-react';
import { getSystemConfig, updateSystemConfig, getTelegramChannels, createTelegramChannel, deleteTelegramChannel } from '../lib/api';
import Modal from '../components/Modal';
import { cn } from '../lib/utils';
import { useToast } from '../hooks/useToast';

interface ConfigItem {
  key: string;
  value: string | number | boolean;
  description?: string;
}

interface Channel {
  id: number;
  name: string;
  channel_id: string;
  is_active: boolean;
}

export default function Settings() {
  const [configs, setConfigs] = useState<ConfigItem[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [channelModal, setChannelModal] = useState(false);
  const [channelForm, setChannelForm] = useState({ name: '', channel_id: '' });
  const [savingChannel, setSavingChannel] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    async function load() {
      try {
        const [configData, channelData] = await Promise.all([
          getSystemConfig(),
          getTelegramChannels(),
        ]);
        setConfigs(configData.items || configData.data || configData.configs || configData || []);
        setChannels(channelData.items || channelData.data || channelData.channels || channelData || []);
      } catch (err) {
        toast('Error al cargar configuración', 'error');
        console.error('Error cargando configuraciones:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const handleSaveConfig = async (key: string, value: string | number | boolean) => {
    setSavingKey(key);
    try {
      await updateSystemConfig(key, value);
      toast('Configuración actualizada', 'success');
    } catch (err) {
      toast('Error al guardar la configuración', 'error');
      console.error('Error guardando configuración:', err);
    } finally {
      setSavingKey(null);
    }
  };

  const handleAddChannel = async () => {
    if (!channelForm.name.trim() || !channelForm.channel_id.trim()) return;
    setSavingChannel(true);
    try {
      await createTelegramChannel({
        name: channelForm.name,
        channel_id: channelForm.channel_id,
      });
      setChannelModal(false);
      setChannelForm({ name: '', channel_id: '' });
      toast('Canal añadido correctamente', 'success');
      const data = await getTelegramChannels();
      setChannels(data.items || data.data || data.channels || data || []);
    } catch (err) {
      toast('Error al añadir el canal', 'error');
      console.error('Error añadiendo canal:', err);
    } finally {
      setSavingChannel(false);
    }
  };

  const handleDeleteChannel = async (id: number) => {
    try {
      await deleteTelegramChannel(id);
      toast('Canal eliminado', 'success');
      const data = await getTelegramChannels();
      setChannels(data.items || data.data || data.channels || data || []);
    } catch (err) {
      toast('Error al eliminar el canal', 'error');
      console.error('Error eliminando canal:', err);
    }
  };

  const handleConfigValueChange = (key: string, value: string) => {
    setConfigs((prev) =>
      prev.map((c) => (c.key === key ? { ...c, value } : c))
    );
  };

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h1 className="page-title">Configuración</h1>
        </div>
        <div className="flex justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Configuración</h1>
      </div>

      <div className="space-y-6">
        {/* General Settings */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-primary-50 text-primary-600 flex items-center justify-center">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">General</h2>
              <p className="text-sm text-gray-500">Configuración general del bot</p>
            </div>
          </div>
          <div className="space-y-4">
            {configs
              .filter((c) => ['bot_token', 'admin_id', 'bot_username'].includes(c.key))
              .map((config) => (
                <div key={config.key} className="flex items-end gap-4">
                  <div className="flex-1">
                    <label className="label capitalize">
                      {config.key.replace(/_/g, ' ')}
                    </label>
                    <input
                      type={config.key === 'bot_token' ? 'password' : 'text'}
                      value={String(config.value)}
                      onChange={(e) => handleConfigValueChange(config.key, e.target.value)}
                      className="input-field font-mono text-sm"
                    />
                    {config.description && (
                      <p className="text-xs text-gray-400 mt-1">{config.description}</p>
                    )}
                  </div>
                  <button
                    onClick={() => handleSaveConfig(config.key, config.value)}
                    disabled={savingKey === config.key}
                    className="btn-primary !py-2"
                  >
                    {savingKey === config.key ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Save className="w-4 h-4" />
                    )}
                    Guardar
                  </button>
                </div>
              ))}
          </div>
        </div>

        {/* Telegram Channels */}
        <div className="card p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                <Send className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Canales de Telegram</h2>
                <p className="text-sm text-gray-500">Canales donde se publican las noticias</p>
              </div>
            </div>
            <button
              onClick={() => setChannelModal(true)}
              className="btn-primary"
            >
              Añadir canal
            </button>
          </div>

          {channels.length === 0 ? (
            <div className="text-center py-8 text-gray-400 text-sm">
              No hay canales configurados
            </div>
          ) : (
            <div className="space-y-2">
              {channels.map((ch) => (
                <div
                  key={ch.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      'w-2 h-2 rounded-full',
                      ch.is_active ? 'bg-green-500' : 'bg-gray-400'
                    )} />
                    <div>
                      <p className="text-sm font-medium text-gray-900">{ch.name}</p>
                      <p className="text-xs text-gray-500 font-mono">{ch.channel_id}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteChannel(ch.id)}
                    className="text-red-400 hover:text-red-600 text-sm font-medium"
                  >
                    Eliminar
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* System Configuration */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-accent-50 text-accent-600 flex items-center justify-center">
              <Settings2 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Sistema</h2>
              <p className="text-sm text-gray-500">Configuración del sistema y scheduler</p>
            </div>
          </div>
          <div className="space-y-4">
            {configs
              .filter((c) =>
                ['fetch_interval', 'max_retries', 'timeout', 'max_news_per_fetch'].includes(c.key)
              )
              .map((config) => (
                <div key={config.key} className="flex items-end gap-4">
                  <div className="flex-1">
                    <label className="label capitalize">
                      {config.key.replace(/_/g, ' ')}
                    </label>
                    <input
                      type="number"
                      value={String(config.value)}
                      onChange={(e) => handleConfigValueChange(config.key, e.target.value)}
                      className="input-field"
                    />
                    {config.description && (
                      <p className="text-xs text-gray-400 mt-1">{config.description}</p>
                    )}
                  </div>
                  <button
                    onClick={() => {
                      const numVal = Number(config.value);
                      handleSaveConfig(config.key, isNaN(numVal) ? config.value : numVal);
                    }}
                    disabled={savingKey === config.key}
                    className="btn-primary !py-2"
                  >
                    {savingKey === config.key ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Save className="w-4 h-4" />
                    )}
                    Guardar
                  </button>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* Add Channel Modal */}
      <Modal
        isOpen={channelModal}
        onClose={() => setChannelModal(false)}
        title="Añadir canal de Telegram"
        size="sm"
        footer={
          <>
            <button
              onClick={() => setChannelModal(false)}
              className="btn-secondary"
            >
              Cancelar
            </button>
            <button
              onClick={handleAddChannel}
              disabled={savingChannel}
              className="btn-primary"
            >
              {savingChannel ? 'Añadiendo...' : 'Añadir'}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="label">Nombre del canal</label>
            <input
              type="text"
              value={channelForm.name}
              onChange={(e) =>
                setChannelForm({ ...channelForm, name: e.target.value })
              }
              className="input-field"
              placeholder="Ej: Noticias Perú"
            />
          </div>
          <div>
            <label className="label">ID del canal</label>
            <input
              type="text"
              value={channelForm.channel_id}
              onChange={(e) =>
                setChannelForm({ ...channelForm, channel_id: e.target.value })
              }
              className="input-field font-mono"
              placeholder="@canal o -100123456789"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
