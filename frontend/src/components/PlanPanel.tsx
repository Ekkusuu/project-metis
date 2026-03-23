import './PlanPanel.css';

export interface PlanTask {
  id: string;
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
}

interface PlanPanelProps {
  tasks: PlanTask[];
  isTyping: boolean;
}

function PlanPanel({ tasks, isTyping }: PlanPanelProps) {
  const hasTasks = tasks.length > 0;

  const getMarker = (status: PlanTask['status']) => {
    if (status === 'completed') return '[x]';
    if (status === 'in_progress') return '[>]';
    return '[ ]';
  };

  return (
    <aside className="plan-panel">
      <div className="plan-panel-header">
        <div>
          <h2>Live Plan</h2>
          <p>{hasTasks ? 'Internal steps for this reply' : 'Waiting for the next turn'}</p>
        </div>
        <span className={`plan-status ${isTyping ? 'active' : 'idle'}`}>{isTyping ? 'RUNNING' : 'IDLE'}</span>
      </div>

      {hasTasks ? (
        <div className="plan-task-list">
          {tasks.map((task, index) => (
            <div key={task.id} className={`plan-task-row ${task.status}`}>
              <div className="plan-task-prefix">{String(index + 1).padStart(2, '0')}</div>
              <div className="plan-task-body">
                <div className="plan-task-line">
                  <span className="plan-task-marker">{getMarker(task.status)}</span>
                  <div className="plan-task-title">{task.content}</div>
                </div>
                <div className="plan-task-meta">{task.status === 'completed' ? 'done' : task.status === 'in_progress' ? 'active' : 'queued'}</div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="plan-empty-state">
          <p>` no active plan`
          <br />
          Send a message to start a run.</p>
        </div>
      )}
    </aside>
  );
}

export default PlanPanel;
