import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
    items: Array<{
      groupKey: string;
      targetConversationId: string;
      targetConversationName: string;
    }>,
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
  const [confirmOpen, setConfirmOpen] = useState(false);

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
      setConfirmOpen(false);
      return;
    }

    setSelectedGroupKeys(newCandidates.map((item) => item.groupKey));
    setAssignments({});
    setBulkKeyword('');
    setBulkConversationId('');
    setError(null);
    setConfirmOpen(false);
  }, [newCandidates, open]);

  const selectedBulkConversation = useMemo(
    () =>
      groupNames.find(
        (groupName) => String(groupName.id) === bulkConversationId,
      ) ?? null,
    [bulkConversationId, groupNames],
  );

  const allSelected =
    newCandidates.length > 0 &&
    newCandidates.every((item) => selectedGroupKeys.includes(item.groupKey));
  const someSelected = !allSelected && selectedGroupKeys.length > 0;

  const handleToggleGroup = (groupKey: string, checked: boolean) => {
    setSelectedGroupKeys((current) => {
      if (checked) {
        return current.includes(groupKey) ? current : [...current, groupKey];
      }
      return current.filter((item) => item !== groupKey);
    });
  };

  const handleSelectAllCurrentPage = (checked: boolean) => {
    if (!checked) {
      setSelectedGroupKeys([]);
      return;
    }
    setSelectedGroupKeys(newCandidates.map((item) => item.groupKey));
  };

  const applyBulkConversationToSelected = () => {
    if (!selectedBulkConversation?.name.trim()) {
      setError(t('broadcast.bulkGroupAssignment.validationError'));
      return;
    }
    setAssignments((current) => {
      const next = { ...current };
      for (const groupKey of selectedGroupKeys) {
        next[groupKey] = String(selectedBulkConversation.id);
      }
      return next;
    });
    setError(null);
  };

  const clearSelectedAssignments = () => {
    setAssignments((current) => {
      const next = { ...current };
      for (const groupKey of selectedGroupKeys) {
        delete next[groupKey];
      }
      return next;
    });
    setError(null);
  };

  const validateBeforeSubmit = () => {
    if (selectedGroupKeys.length === 0) {
      setError(t('broadcast.bulkGroupAssignment.validationError'));
      return false;
    }
    const missingAssignmentCount = selectedGroupKeys.filter(
      (groupKey) => !assignments[groupKey]?.trim(),
    ).length;
    if (missingAssignmentCount > 0) {
      setError(
        t('broadcast.bulkGroupAssignment.validationErrorWithCount', {
          count: missingAssignmentCount,
        }),
      );
      return false;
    }
    setError(null);
    return true;
  };

  const confirmSubmit = async () => {
    await onSubmit(
      selectedGroupKeys.map((groupKey) => {
        const selectedGroup = groupNames.find(
          (groupName) => String(groupName.id) === assignments[groupKey],
        );
        return {
          groupKey,
          targetConversationId:
            selectedGroup?.externalConversationId?.trim() ?? '',
          targetConversationName: selectedGroup?.name ?? '',
        };
      }),
    );
    setConfirmOpen(false);
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent
          className="max-h-[85vh] overflow-y-auto sm:max-w-6xl"
          data-testid="broadcast-group-matching-bulk-assign-dialog"
        >
          <DialogHeader>
            <DialogTitle>
              {t('broadcast.bulkGroupAssignment.title')}
            </DialogTitle>
            <DialogDescription>
              {t('broadcast.bulkGroupAssignment.description', {
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
                groupNames={groupNames}
                value={bulkConversationId}
                keyword={bulkKeyword}
                onKeywordChange={setBulkKeyword}
                onChange={(conversation) => {
                  setBulkConversationId(
                    conversation ? String(conversation.id) : '',
                  );
                  setError(null);
                }}
                disabled={loading || submitting}
                searchLabel={t(
                  'broadcast.bulkGroupAssignment.searchConversation',
                )}
                searchPlaceholder={t(
                  'broadcast.bulkGroupAssignment.searchPlaceholder',
                )}
                emptyLabel={t('broadcast.bulkGroupAssignment.noCandidates')}
                missingStableIdLabel={t(
                  'broadcast.bulkGroupAssignment.missingStableId',
                )}
                searchInputTestId="broadcast-group-matching-bulk-assign-search-input"
                listTestId="broadcast-group-matching-bulk-assign-search-results"
              />
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  data-testid="broadcast-group-matching-bulk-assign-apply-button"
                  disabled={
                    loading ||
                    submitting ||
                    !selectedBulkConversation?.name.trim() ||
                    selectedGroupKeys.length === 0
                  }
                  onClick={applyBulkConversationToSelected}
                >
                  {t('broadcast.bulkGroupAssignment.applyToSelected', {
                    count: selectedGroupKeys.length,
                  })}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  disabled={selectedGroupKeys.length === 0 || submitting}
                  onClick={clearSelectedAssignments}
                >
                  {t('broadcast.bulkGroupAssignment.clearSelected')}
                </Button>
              </div>
            </div>

            <div className="space-y-3">
              <div className="rounded-lg border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-12">
                        <Checkbox
                          checked={
                            allSelected
                              ? true
                              : someSelected
                                ? 'indeterminate'
                                : false
                          }
                          disabled={
                            loading || submitting || newCandidates.length === 0
                          }
                          onCheckedChange={(checked) =>
                            handleSelectAllCurrentPage(checked === true)
                          }
                        />
                      </TableHead>
                      <TableHead>
                        {t('broadcast.bulkGroupAssignment.customerName')}
                      </TableHead>
                      <TableHead>
                        {t('broadcast.bulkGroupAssignment.rawRowCount')}
                      </TableHead>
                      <TableHead>
                        {t('broadcast.bulkGroupAssignment.status')}
                      </TableHead>
                      <TableHead>
                        {t('broadcast.bulkGroupAssignment.targetConversation')}
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell
                          colSpan={5}
                          className="text-center text-muted-foreground"
                        >
                          {t('common.loading')}
                        </TableCell>
                      </TableRow>
                    ) : null}
                    {!loading && newCandidates.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={5}
                          className="text-center text-muted-foreground"
                        >
                          {t('broadcast.bulkGroupAssignment.noCandidates')}
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
                            <TableCell>{item.customerName}</TableCell>
                            <TableCell>{item.rawRowCount}</TableCell>
                            <TableCell>
                              {t(
                                `broadcast.bulkGroupAssignment.statusValues.${item.status}`,
                              )}
                            </TableCell>
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
                                    'broadcast.bulkGroupAssignment.targetConversationSelectPlaceholder',
                                  )}
                                </option>
                                {groupNames.map((groupName) => {
                                  const stableId =
                                    groupName.externalConversationId?.trim();
                                  return (
                                    <option
                                      key={groupName.id}
                                      value={String(groupName.id)}
                                    >
                                      {stableId
                                        ? groupName.name
                                        : `${groupName.name} · ${t('broadcast.groupRule.targetResolution.deferred')}`}
                                    </option>
                                  );
                                })}
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
              data-testid="broadcast-group-matching-bulk-assign-submit-button"
              disabled={loading || submitting || newCandidates.length === 0}
              onClick={() => {
                if (validateBeforeSubmit()) {
                  setConfirmOpen(true);
                }
              }}
            >
              {t('broadcast.bulkGroupAssignment.submit', {
                count: selectedGroupKeys.length,
              })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent data-testid="broadcast-group-matching-bulk-assign-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('broadcast.bulkGroupAssignment.confirmTitle')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('broadcast.bulkGroupAssignment.confirmDescription', {
                count: selectedGroupKeys.length,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              data-testid="broadcast-group-matching-bulk-assign-confirm-button"
              onClick={(event) => {
                event.preventDefault();
                void confirmSubmit();
              }}
            >
              {submitting
                ? t('broadcast.bulkGroupAssignment.submitting')
                : t('broadcast.bulkGroupAssignment.submit', {
                    count: selectedGroupKeys.length,
                  })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
