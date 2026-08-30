# Unexpected attribute 'label_size' error when using plot_multiple with Bokeh

I'm trying to visualize multiple profiler results using the `plot_multiple` function, but I'm running into an error.

## Expected Result

The `plot_multiple` function should successfully create a visualization of multiple profiler results.

## Actual Result

I get an `AttributeError` about an unexpected attribute 'label_size':

```
AttributeError: unexpected attribute 'label_size' to figure, possible attributes are above, active_drag, active_inspect, active_multi, active_scroll, active_tap, align, aspect_ratio, aspect_scale, attribution, background_fill_alpha, background_fill_color, below, border_fill_alpha, border_fill_color, center, context_menu, css_classes, css_variables, disabled, elements, extra_x_ranges, extra_x_scales, extra_y_ranges, extra_y_scales, flow_mode, frame_align, frame_height, frame_width, height, height_policy, hidpi, hold_render, inner_height, inner_width, js_event_callbacks, js_property_callbacks, left, lod_factor, lod_interval, lod_threshold, lod_timeout, margin, match_aspect, max_height, max_width, min_border, min_border_bottom, min_border_left, min_border_right, min_border_top, min_height, min_width, name, outer_height, outer_width, outline_line_alpha, outline_line_cap, outline_line_color, outline_line_dash, outline_line_dash_offset, outline_line_join, outline_line_width, output_backend, renderers, reset_policy, resizable, right, sizing_mode, styles, stylesheets, subscribed_events, syncable, tags, title, title_location, toolbar, toolbar_inner, toolbar_location, toolbar_sticky, tools, tooltips, visible, width, width_policy, x_axis_label, x_axis_location, x_axis_type, x_minor_ticks, x_range, x_scale, y_axis_label, y_axis_location, y_axis_type, y_minor_ticks, y_range or y_scale
```

## Reproduction Steps

```python
import dask
from dask.diagnostics import Profiler, ResourceProfiler, CacheProfiler
from dask.diagnostics.profile_visualize import visualize

# Create a simple computation
def inc(x):
    return x + 1

def add(x, y):
    return x + y

dsk = {'x': 1, 'y': (inc, 'x'), 'z': (add, 'y', 10)}

# Set up the profilers
profilers = [Profiler(), ResourceProfiler(), CacheProfiler()]

# Run the computation with the profilers
with dask.config.set(scheduler='sync'):
    with Profiler() as prof:
        with ResourceProfiler() as rprof:
            with CacheProfiler() as cprof:
                out = dask.get(dsk, 'z')

# Try to visualize the results
visualize([prof, rprof, cprof])  # This raises the AttributeError
```

## System Information

- Dask version: latest
- Bokeh version: 3.x
- Python version: 3.10

It seems like there might be an issue with how the `label_size` parameter is being handled when visualizing multiple profiler results, especially with Bokeh 3.x.
