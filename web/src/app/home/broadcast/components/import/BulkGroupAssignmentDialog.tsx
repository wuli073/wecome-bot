import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import GroupConversationSelector from '../shared/GroupConversationSelector';
import type {
  BroadcastGroupName,
  BroadcastGroupRuleCandidateList,
} from '../../types';

interface BulkGroupAssignmentDialogProps {
  open: boolean;
  loading?: boolean;
  submitting?: boolean;
  candidates: BroadcastGroupRuleCandidateList | null;
  groupNames: BroadcastGroupName[];
  onOpenChange: (open: boolean) => void;
  onSubmit: (
    items: Array<{ groupKey: string; targetConversationId: string }>,
  ) => Promise<void>;
}

export default function BulkGroupAssignmentDialog({
  open,
  loading = false,
  submitting = false,
  candidates,
  groupNames,
  onOpenChange,
  onSubmit,
}: BulkGroupAssignmentDialogProps) {
  const { t } = useTranslation();
  const [selectedGroupKeys, setSelectedGroupKeys] = useState<string[]>([]);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [bulkKeyword, setBulkKeyword] = useState('');
  const [bulkConversationId, setBulkConversationId] = useState('');
  const [error, setError] = useState<string | null>(null);

  const selectableGroupNames = useMemo(
    () =>
      groupNames.filter((groupName) =>
        Boolean(groupName.externalConversationId?.trim()),
      ),
    [groupNames],
  );

  const newCandidates = useMemo(
    () => candidates?.items.filter((item) => item.status === 'new') ?? [],
    [candidates],
  );

  useEffect(() => {
    if (!open) {
      setSelectedGroupKeys([]);
      setAssignments({});
      setBulkKeyword('');
      setBulkConversationId('');
      setError(null);
      return;
    }
    setSelectedGroupKeys(newCandidates.map((item) => item.groupKey));
    setAssignments({});
    setBulkKeyword('');
    setBulkConversationId('');
    setError(null);
  }, [newCandidates, open]);

  const selectedBulkConversation = useMemo(
    () =>
      selectableGroupNames.find(
        (groupName) => groupName.externalConversationId === bulkConversationId,
      ) ?? null,
    [bulkConversationId, selectableGroupNames],
  );

  const handleToggleGroup = (groupKey: string, checked: boolean) => {
    setSelectedGroupKeys((current) => {
      if (checked) {
        return current.includes(groupKey) ? current : [...current, groupKey];
      }
      return current.filter((item) => item !== groupKey);
    });
  };

  const applyBulkConversationToSelected = () => {
    if (!selectedBulkConversation?.externalConversationId) {
      setError(t('broadcast.import.bulkAssign.selectionRequired'));
      return;
    }
    setAssignments((current) => {
      const next = { ...current };
      selectedGroupKeys.forEach((groupKey) => {
        next[groupKey] = selectedBulkConversation.externalConversationId ?? '';
      });
      return next;
    });
    setError(null);
  };

  const handleSubmit = async () => {
    if (selectedGroupKeys.length === 0) {
      setError(t('broadcast.import.bulkAssign.noSelection'));
      return;
    }
    const missingAssignmentCount = selectedGroupKeys.filter(
      (groupKey) => !assignments[groupKey]?.trim(),
    ).length;
    if (missingAssignmentCount > 0) {
      setError(
        t('broadcast.import.bulkAssign.missingAssignments', {
          count: missingAssignmentCount,
        }),
      );
      return;
    }
    setError(null);
    await onSubmit(
      selectedGroupKeys.map((groupKey) => ({
        groupKey,
        targetConversationId: assignments[groupKey],
      })),
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[85vh] overflow-y-auto sm:max-w-5xl"
        data-testid="broadcast-import-bulk-assign-dialog"
      >
        <DialogHeader>
          <DialogTitle>
            {t('broadcast.import.bulkAssign.dialogTitle')}
          </DialogTitle>
          <DialogDescription>
            {t('broadcast.import.bulkAssign.dialogDescription', {
              count: newCandidates.length,
            })}
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-3">
            <GroupConversationSelector
              groupNames={selectableGroupNames}
              value={bulkConversationId}
              keyword={bulkKeyword}
              onKeywordChange={setBulkKeyword}
              onChange={(conversation) => {
                setBulkConversationId(
                  conversation?.externalConversationId ?? '',
                );
                setError(null);
              }}
              disabled={loading || submitting}
              searchLabel={t(
                'broadcast.import.bulkAssign.applyConversationLabel',
              )}
              searchPlaceholder={t(
                'broadcast.import.bulkAssign.searchPlaceholder',
              )}
              emptyLabel={t('broadcast.import.bulkAssign.emptySearch')}
              searchInputTestId="broadcast-import-bulk-assign-search-input"
              listTestId="broadcast-import-bulk-assign-search-results"
            />
            <Button
              type="button"
              variant="outline"
              disabled={
                loading ||
                submitting ||
                !selectedBulkConversation?.externalConversationId ||
                selectedGroupKeys.length === 0
              }
              onClick={applyBulkConversationToSelected}
            >
              {t('broadcast.import.bulkAssign.applyConversationButton', {
                count: selectedGroupKeys.length,
              })}
            </Button>
          </div>

          <div className="space-y-3">
            <div className="rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">
                      {t('broadcast.import.bulkAssign.tableHeaders.selection')}
                    </TableHead>
                    <TableHead>
                      {t(
                        'broadcast.import.bulkAssign.tableHeaders.customerName',
                      )}
                    </TableHead>
                    <TableHead>
                      {t(
                        'broadcast.import.bulkAssign.tableHeaders.rawRowCount',
                      )}
                    </TableHead>
                    <TableHead>
                      {t(
                        'broadcast.import.bulkAssign.tableHeaders.targetConversation',
                      )}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell
                        colSpan={4}
                        className="text-center text-muted-foreground"
                      >
                        {t('common.loading')}
                      </TableCell>
                    </TableRow>
                  ) : null}
                  {!loading && newCandidates.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={4}
                        className="text-center text-muted-foreground"
                      >
                        {t('broadcast.import.bulkAssign.emptyCandidates')}
                      </TableCell>
                    </TableRow>
                  ) : null}
                  {!loading
                    ? newCandidates.map((item) => (
                        <TableRow key={item.groupKey}>
                          <TableCell>
                            <Checkbox
                              checked={selectedGroupKeys.includes(
                                item.groupKey,
                              )}
                              disabled={submitting}
                              onCheckedChange={(checked) =>
                                handleToggleGroup(
                                  item.groupKey,
                                  checked === true,
                                )
                              }
                            />
                          </TableCell>
                          <TableCell>
                            <div className="font-medium">
                              {item.customerName}
                            </div>
                          </TableCell>
                          <TableCell>{item.rawRowCount}</TableCell>
                          <TableCell>
                            <select
                              className="border-input bg-background h-9 w-full rounded-md border px-3 py-2 text-sm"
                              value={assignments[item.groupKey] ?? ''}
                              disabled={submitting}
                              onChange={(event) => {
                                const nextConversationId = event.target.value;
                                setAssignments((current) => ({
                                  ...current,
                                  [item.groupKey]: nextConversationId,
                                }));
                                setError(null);
                              }}
                            >
                              <option value="">
                                {t(
                                  'broadcast.import.bulkAssign.targetConversationPlaceholder',
                                )}
                              </option>
                              {selectableGroupNames.map((groupName) => (
                                <option
                                  key={groupName.id}
                                  value={groupName.externalConversationId ?? ''}
                                >
                                  {groupName.name}
                                </option>
                              ))}
                            </select>
                          </TableCell>
                        </TableRow>
                      ))
                    : null}
                </TableBody>
              </Table>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            {t('common.cancel')}
          </Button>
          <Button
            type="button"
            disabled={loading || submitting || newCandidates.length === 0}
            onClick={() => void handleSubmit()}
          >
            {t('broadcast.import.bulkAssign.submitButton', {
              count: selectedGroupKeys.length,
            })}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
