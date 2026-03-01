#ifdef HAVE_CONFIG_H
#include <fc_config.h>
#endif

#include <stdlib.h>

/* gui main header */
#include "gui_stub.h"

/* utility */
#include "log.h"
#include "mem.h"

#include "sprite.h"

/************************************************************************//**
  Return a nullptr-terminated, permanently allocated array of possible
  graphics types extensions. Extensions listed first will be checked first.
****************************************************************************/
const char **gfx_fileextensions(void)
{
  /* PORTME */

  /* Hack to allow stub to run */
  static const char *ext[] = {
    "png",	/* png should be the default. */
    /* ...etc... */
    nullptr
  };

  return ext;
}

/************************************************************************//**
  Load the given graphics file into a sprite. This function loads an
  entire image file, which may later be broken up into individual sprites
  with crop_sprite().
****************************************************************************/
struct sprite *gui_load_gfxfile(const char *filename, bool svgflag)
{
  struct sprite *sprite = fc_malloc(sizeof(*sprite));

  if (filename) {
    sprite->surface = cairo_image_surface_create_from_png(filename);
    if (cairo_surface_status(sprite->surface) != CAIRO_STATUS_SUCCESS) {
      log_debug("Failed to load PNG file: %s (status: %d)", filename,
                cairo_surface_status(sprite->surface));
      cairo_surface_destroy(sprite->surface);
      /* Create a placeholder surface instead of returning NULL */
      sprite->surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 1, 1);
    }
  } else {
    /* Create a placeholder surface */
    sprite->surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 1, 1);
  }

  return sprite;
}

/************************************************************************//**
  Create a new sprite by cropping and taking only the given portion of
  the image.

  source gives the sprite that is to be cropped.

  x,y, width, height gives the rectangle to be cropped. The pixel at
  position of the source sprite will be at (0,0) in the new sprite, and
  the new sprite will have dimensions (width, height).

  mask gives an additional mask to be used for clipping the new
  sprite. Only the transparency value of the mask is used in
  crop_sprite. The formula is: dest_trans = src_trans * mask_trans.
  Note that because the transparency is expressed as an
  integer it is common to divide it by 256 afterwards.

  mask_offset_x, mask_offset_y is the offset of the mask relative to the
  origin of the source image. The pixel at (mask_offset_x, mask_offset_y)
  in the mask image will be used to clip pixel (0, 0) in the source image
  which is pixel (-x, -y) in the new image.
****************************************************************************/
struct sprite *gui_crop_sprite(struct sprite *source,
                               int x, int y, int width, int height,
                               struct sprite *mask,
                               int mask_offset_x, int mask_offset_y,
                               float scale, bool smooth)
{
  struct sprite *new = fc_malloc(sizeof(*new));
  cairo_t *cr;

  fc_assert_ret_val(source, NULL);
  fc_assert_ret_val(source->surface, NULL);

  new->surface = cairo_surface_create_similar(source->surface,
          CAIRO_CONTENT_COLOR_ALPHA, width, height);
  cr = cairo_create(new->surface);
  cairo_rectangle(cr, 0, 0, width, height);
  cairo_clip(cr);

  cairo_set_source_surface(cr, source->surface, -x, -y);
  cairo_paint(cr);
  if (mask && mask->surface) {
    cairo_set_operator(cr, CAIRO_OPERATOR_DEST_IN);
    cairo_set_source_surface(cr, mask->surface, mask_offset_x-x, mask_offset_y-y);
    cairo_paint(cr);
  }
  cairo_destroy(cr);

  return new;
}

/************************************************************************//**
  Create a new sprite with the given width, height, and color.
****************************************************************************/
struct sprite *gui_create_sprite(int width, int height, struct color *pcolor) {
  struct sprite *sprite = fc_malloc(sizeof(*sprite));
  cairo_t *cr;

  fc_assert_ret_val(width > 0, NULL);
  fc_assert_ret_val(height > 0, NULL);
  fc_assert_ret_val(pcolor != NULL, NULL);

  sprite->surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32,
         width, height);

  cr = cairo_create(sprite->surface);

  cairo_paint(cr);
  cairo_destroy(cr);

  return sprite;
}

/************************************************************************//**
  Find the dimensions of the sprite.
****************************************************************************/
void gui_get_sprite_dimensions(struct sprite *sprite, int *width, int *height) {
  if (sprite && sprite->surface) {
    *width = cairo_image_surface_get_width(sprite->surface);
    *height = cairo_image_surface_get_height(sprite->surface);
  } else {
    *width = 0;
    *height = 0;
  }
}

/************************************************************************//**
  Free a sprite and all associated image data.
****************************************************************************/
void gui_free_sprite(struct sprite *s)
{
  if (s) {
    if (s->surface) {
      cairo_surface_destroy(s->surface);
    }
    free(s);
  }
}

/************************************************************************//**
  Return a sprite image of a number.
****************************************************************************/
struct sprite *gui_load_gfxnumber(int num)
{
  struct sprite *sprite = fc_malloc(sizeof(*sprite));
  sprite->surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 1, 1);
  return sprite;
}
