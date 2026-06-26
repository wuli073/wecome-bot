/**
 * Database Mode Redirect
 * Redirects /home/database-mode to the appropriate bot's sessions tab
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { backendClient } from '@/app/infra/http';
import { toast } from 'sonner';

export default function DatabaseModeRedirect() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function redirect() {
      try {
        const res = await backendClient.getBots();
        const databaseBots = res.bots.filter(
          (b) => b.adapter === 'wxwork_database' && b.enable,
        );

        if (databaseBots.length === 1) {
          // Redirect to the bot's session monitor tab
          navigate(`/home/bots?id=${databaseBots[0].uuid}&tab=sessions`, {
            replace: true,
          });
        } else if (databaseBots.length === 0) {
          // No enabled database mode bot found
          navigate('/home/bots', { replace: true });
          toast.info('Please create or enable a "WeCom Database Mode" bot');
        } else {
          // Multiple database mode bots, go to bots list
          navigate('/home/bots', { replace: true });
          toast.info('Multiple database mode bots found. Please select one.');
        }
      } catch (error) {
        console.error('Failed to redirect:', error);
        navigate('/home/bots', { replace: true });
        toast.error('Failed to load bot information');
      } finally {
        setLoading(false);
      }
    }

    redirect();
  }, [navigate]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-muted-foreground">Redirecting...</div>
      </div>
    );
  }

  return null;
}
