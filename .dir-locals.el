((c-mode
  (c-file-style . "k&r")
  (c-basic-offset . 2)
  (indent-tabs-mode . nil)
  (tab-width . 8)           ; existing code uses 8-wide tabs
  (fill-column . 77)        ; "Lines are at most 77 characters long"
  (require-final-newline . t)
  (c-offsets-alist
   (case-label . 0)))       ; case labels flush with enclosing switch

 (c++-mode
  (c-file-style . "k&r")
  (c-basic-offset . 2)
  (indent-tabs-mode . nil)
  (tab-width . 8)
  (fill-column . 77)
  (require-final-newline . t)
  (c-offsets-alist
   (case-label . 0))))
