export const STATUS_LABEL = {
  applied: 'Applied', screening: 'Screening', interview: 'Interview',
  assessment: 'Assessment', offer: 'Offer', rejected: 'Rejected',
  offer_accepted: 'Accepted', offer_declined: 'Declined',
  withdrawn: 'Withdrawn', ghosted: 'Ghosted',
};

export const STATUS_OPTIONS = [
  { value: 'applied', label: 'Applied' },
  { value: 'screening', label: 'Screening' },
  { value: 'interview', label: 'Interview' },
  { value: 'assessment', label: 'Assessment' },
  { value: 'offer', label: 'Offer' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'ghosted', label: 'Ghosted' },
  { value: 'withdrawn', label: 'Withdrawn' },
];

export const SOURCE_OPTIONS = [
  { value: 'manual', label: 'Manual' },
  { value: 'resume_generator', label: 'Resume Generator' },
];

export const WORK_TYPE_OPTIONS = [
  { value: '', label: '— None —' },
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'onsite', label: 'Onsite' },
];
