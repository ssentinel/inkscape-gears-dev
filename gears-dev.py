#! /usr/bin/env python
# -*- coding: utf-8 -*-
'''
Copyright (C) 2007 Aaron Spike  (aaron @ ekips.org)
Copyright (C) 2007 Tavmjong Bah (tavmjong @ free.fr)
Copyright (C) http://cnc-club.ru/forum/viewtopic.php?f=33&t=434&p=2594#p2500
Copyright (C) 2014 Jürgen Weigert (juewei@fabfolk.com)

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

2014-03-20 jw@suse.de 0.2  Option --accuracy=0 for automatic added.
2014-03-21                 sent upstream: https://bugs.launchpad.net/inkscape/+bug/1295641
2014-03-21 jw@suse.de 0.3  Fixed center of rotation for gears with odd number of teeth.
2014-04-04 juewei     0.7  Revamped calc_unit_factor(). 
2014-04-05 juewei    0.7a  Correctly positioned rack gear.
	       	           The geometry above the meshing line is wrong.
2014-04-06 juewei    0.7b  Undercut detection added. Reference:
			   http://nptel.ac.in/courses/IIT-MADRAS/Machine_Design_II/pdf/2_2.pdf
			   Manually merged https://github.com/jnweiger/inkscape-gears-dev/pull/15
'''

import inkex
import simplestyle, sys, os
from math import *

__version__ = '0.7b'


def linspace(a,b,n):
    """ return list of linear interp of a to b in n steps
        - if a and b are ints - you'll get an int result.
        - n must be an integer
    """
    return [a+x*(b-a)/(n-1) for x in range(0,n)]

def involute_intersect_angle(Rb, R):
    Rb, R = float(Rb), float(R)
    return (sqrt(R**2 - Rb**2) / (Rb)) - (acos(Rb / R))

def point_on_circle(radius, angle):
    " return xy coord of the point at distance radius from origin at angle "
    x = radius * cos(angle)
    y = radius * sin(angle)
    return (x, y)
    
def points_to_bbox(p):
    """ from a list of points (x,y pairs)
        - return the lower-left xy and upper-right xy
    """
    llx = urx = p[0][0]
    lly = ury = p[0][1]
    for x in p[1:]:
        if   x[0] < llx: llx = x[0]
        elif x[0] > urx: urx = x[0]
        if   x[1] < lly: lly = x[1]
        elif x[1] > ury: ury = x[1]
    return (llx, lly, urx, ury)

def points_to_bbox_center(p):
    """ from a list of points (x,y pairs)
        - find midpoint of bounding box around all points
        - return (x,y)
    """
    bbox = points_to_bbox(p)
    return ((bbox[0]+bbox[2])/2.0, (bbox[1]+bbox[3])/2.0)
                
def points_to_svgd(p):
    " convert list of points into a closed SVG path list"
    f = p[0]
    p = p[1:]
    svgd = 'M%.4f,%.4f' % f
    for x in p:
        svgd += 'L%.4f,%.4f' % x
    svgd += 'z'
    return svgd

def draw_SVG_circle(parent, r, cx, cy, name, style):
    " add an SVG circle entity to parent "
    circ_attribs = {'style': simplestyle.formatStyle(style),
                    'cx': str(cx), 'cy': str(cy), 
                    'r': str(r),
                    inkex.addNS('label','inkscape'):name}
    circle = inkex.etree.SubElement(parent, inkex.addNS('circle','svg'), circ_attribs )


def undercut_min_teeth(pitch_angle, k=1.0):
    """ computes the minimum tooth count for a 
        spur gear so that no undercut with the given pitch_angle (in deg) 
        and an addendum = k * metric_module, where 0 < k < 1
	Note:
	The return value should be rounded upwards for perfect safety. E.g.
	min_teeth = int(math.ceil(undercut_min_teeth(20.0)))	# 18, not 17
    """
    x = sin(radians(pitch_angle))
    return 2*k/(x*x)

def undercut_max_k(teeth, pitch_angle=20.0):
    """ computes the maximum k value for a given teeth count and pitch_angle
        so that no undercut occurs.
    """
    x = sin(radians(pitch_angle))
    return 0.5 * teeth * x * x

def undercut_min_angle(teeth, k=1.0):
    """ computes the minimum pitch angle, to that the given teeth count (and
        profile shift) cause no undercut.
    """
    return degrees(asin(min(0.9135, sqrt(2.0*k/teeth))))	# max 59.9 deg


def have_undercut(teeth, pitch_angle=20.0, k=1.0):
    """ returns true if the specified gear dimensions would
        cause an undercut.
    """
    if (teeth < undercut_min_teeth(pitch_angle, k)):
      return True
    else:
      return False


## unused code. arbitrary constants 2.157 and 1.157 are not acceptable.
def gear_calculations(num_teeth, metric, module, circular_pitch, pressure_angle, clearance):
    """ intention is to put base calcs for gear in one place.
        - does not calc for stub teeth just regular
        - pulled from web - might not be the right core list for this program
    """
    if metric:
        # have unneccssary duplicates for inch/metric
        #  probably only one needs to be calculated.
        #  I.e. calc module and derive rest from there.
        #  or calc dp ?
        diametral_pitch = 25.4 / module # dp in inches but does it have to be - probably not
        pitch_diameter = module * num_teeth
        addendum = module
        #dedendum = 1.157 * module # what is 1.157 ?? a clearance calc ?
        dedendum = module + clearance # or maybe combine?  max(module + clearance, 1.157 * module)
        working_depth = 2 * module
        whole_depth = 2.157 * module
        outside_diameter = module * (num_teeth + 2)
    else:
        diametral_pitch = pi / circular_pitch
        pitch_diameter = num_teeth / diametral_pitch
        addendum = 1 / diametral_pitch
        dedendum = 1.157 / diametral_pitch # ?? number from ?
        working_depth = 2 / diametral_pitch
        whole_depth = 2.157 / diametral_pitch
        outside_diameter = (num_teeth + 2) / diametral_pitch
    #
    pitch_radius = pitch_diameter / 2.0
    base_radius = pitch_diameter * cos(pressure_angle) / 2.0
    outer_radius = pitch_radius + addendum
    root_radius =  pitch_radius - dedendum
    # Tooth thickness: Tooth width along pitch circle.
    tooth_thickness  = ( pi * pitch_diameter ) / ( 2.0 * num_teeth )
    #
    return (pitch_radius, base_radius,
            addendum, dedendum, outer_radius, root_radius,
            tooth_thickness
            )

 

def generate_rack_path(tooth_count, pitch, addendum, pressure_angle,
                       base_height, tab_length, clearance=0, draw_guides=False):
        """ Return path (suitable for svg) of the Rack gear.
            - rack gear uses straight sides
                - involute on a circle of infinite radius is a simple linear ramp
	    - the meshing circle touches at y = 0, 
	    - the highest elevation of the teeth is at y = +addednum
	    - the lowest elevation of the teeth is at y = -addednum-clearance
	    - the base_height extends downwards from the lowest elevation.
	    - we generate iths middle tooth exactly centered on the y=0 line.
	      (one extra tooth on the right hand side, if nr of teeth is even)
        """
        spacing = 0.5 * pitch # rolling one pitch distance on the spur gear pitch_diameter.
        # roughly center rack in drawing, exact position is so that it meshes
	# nicely with the spur gear.
	# -0.5*spacing has a gap in the center.
	# +0.5*spacing has a tooth in the center.
	fudge = +0.5 * spacing

        tas  = tan(radians(pressure_angle)) * addendum
        tasc = tan(radians(pressure_angle)) * (addendum+clearance)
	base_top = addendum+clearance
	base_bot = addendum+clearance+base_height

        x_lhs = -pitch * int(0.5*tooth_count-.5) - spacing - tab_length - tasc + fudge
        #inkex.debug("angle=%s spacing=%s"%(pressure_angle, spacing))
        # Start with base tab on LHS
        points = [] # make list of points
        points.append((x_lhs, base_bot))
        points.append((x_lhs, base_top))
        x = x_lhs + tab_length+tasc

        # An involute on a circle of infinite radius is a simple linear ramp.
        # We need to add curve at bottom and use clearance.
        for i in range(tooth_count):
            # move along path, generating the next 'tooth'
            # pitch line is at y=0. the left edge hits the pitch line at x
            points.append((x-tasc, base_top))
            points.append((x+tas, -addendum))
            points.append((x+spacing-tas, -addendum))
            points.append((x+spacing+tasc, base_top)) 
            x += pitch
        x -= spacing # remove last adjustment
        # add base on RHS
	x_rhs = x+tasc+tab_length
        points.append((x_rhs, base_top))
        points.append((x_rhs, base_bot))
	# We don't close the path here. Caller does it.
        # points.append((x_lhs, base_bot))

        # Draw line representing the pitch circle of infinite diameter
        guide = None
        if draw_guides:
            p = []
            p.append( (x_lhs + 0.5 * tab_length, 0) )
            p.append( (x_rhs - 0.5 * tab_length, 0) )
            guide = points_to_svgd(p)
        # return points ready for use in an SVG 'path'
        return (points_to_svgd(points), guide)


class Gears(inkex.Effect):
    def __init__(self):
        inkex.Effect.__init__(self)
        # try using inkex.debug(string) instead...
        try:
            self.tty = open("/dev/tty", 'w')
        except:
            self.tty = open(os.devnull, 'w')  # '/dev/null' for POSIX, 'nul' for Windows.
            # print >>self.tty, "gears-dev " + __version__
        self.OptionParser.add_option("-t", "--teeth",
                                     action="store", type="int",
                                     dest="teeth", default=24,
                                     help="Number of teeth")
        
        self.OptionParser.add_option("-s", "--system",
                                     action="store", type="string", 
                                     dest="system", default='CP',
                                     help="Select system: 'CP' (Cyclic Pitch (default)), 'DP' (Diametral Pitch), 'MM' (Metric Module)")
        
        self.OptionParser.add_option("-d", "--dimension",
                                     action="store", type="float",
                                     dest="dimension", default=1.0,
                                     help="Tooth size, depending on system (which defaults to CP)")


        self.OptionParser.add_option("-a", "--angle",
                                     action="store", type="float",
                                     dest="angle", default=20.0,
                                     help="Pressure Angle (common values: 14.5, 20, 25 degrees)")

        self.OptionParser.add_option("-u", "--units",
                                     action="store", type="string",
                                     dest="units", default='mm',
                                     help="Units this dialog is using")

        self.OptionParser.add_option("-A", "--accuracy",
                                     action="store", type="int",
                                     dest="accuracy", default=0,
                                     help="Accuracy of involute: automatic: 5..20 (default), best: 20(default), medium 10, low: 5; good acuracy is important with a low tooth count")
        # Clearance: Radial distance between top of tooth on one gear to bottom of gap on another.
        self.OptionParser.add_option("", "--clearance",
                                     action="store", type="float",
                                     dest="clearance", default=0.0,
                                     help="Clearance between bottom of gap of this gear and top of tooth of another")

        self.OptionParser.add_option("", "--annotation",
                                     action="store", type="inkbool", 
                                     dest="annotation", default=False,
                                     help="Draw annotation text")

        self.OptionParser.add_option("-R", "--ring",
                                     action="store", type="inkbool",
                                     dest="spur_ring", default=False,
                                     help="Ring gear style (default: normal spur gear)")

        self.OptionParser.add_option("", "--mount-hole",
                                     action="store", type="float",
                                     dest="mount_hole", default=5,
                                     help="Mount hole diameter")

        self.OptionParser.add_option("", "--mount-diameter",
                                     action="store", type="float",
                                     dest="mount_diameter", default=15,
                                     help="Mount support diameter")

        self.OptionParser.add_option("", "--spoke-count",
                                     action="store", type="int",
                                     dest="spoke_count", default=3,
                                     help="Spokes count")

        self.OptionParser.add_option("", "--spoke-width",
                                     action="store", type="float",
                                     dest="spoke_width", default=5,
                                     help="Spoke width")

        self.OptionParser.add_option("", "--holes-rounding",
                                     action="store", type="float",
                                     dest="holes_rounding", default=5,
                                     help="Holes rounding")

        self.OptionParser.add_option("", "--active-tab",
                                     action="store", type="string",
                                     dest="active_tab", default='',
                                     help="Active tab. Not used now.")
                        
        self.OptionParser.add_option("-x", "--centercross",
                                     action="store", type="inkbool", 
                                     dest="centercross", default=False,
                                     help="Draw cross in center")
        
        self.OptionParser.add_option("-c", "--pitchcircle",
                                     action="store", type="inkbool",
                                     dest="pitchcircle", default=False,
                                     help="Draw pitch circle (for mating)")

        self.OptionParser.add_option("-r", "--draw-rack",
                                     action="store", type="inkbool", 
                                     dest="drawrack", default=False,
                                     help="Draw rack gear instead of spur gear")
        
        self.OptionParser.add_option("", "--rack-teeth-length",
                                     action="store", type="int",
                                     dest="teeth_length", default=12,
                                     help="Length (in teeth) of rack")
        
        self.OptionParser.add_option("", "--rack-base-height",
                                     action="store", type="float",
                                     dest="base_height", default=8,
                                     help="Height of base of rack")
        
        self.OptionParser.add_option("", "--rack-base-tab",
                                     action="store", type="float",
                                     dest="base_tab", default=14,
                                     help="Length of tabs on ends of rack")

    
    def add_text(self, node, text, position, text_height=12):
        """ Create and insert a single line of text into the svg under node.
            - use 'text' type and label as anootation
            - where color is Ponoko Orange - so ignored when lasercutting
        """
        line_style = {'font-size': '%dpx' % text_height, 'font-style':'normal', 'font-weight': 'normal',
                     'fill': '#F6921E', 'font-family': 'Bitstream Vera Sans,sans-serif',
                     'text-anchor': 'middle', 'text-align': 'center'}
        line_attribs = {inkex.addNS('label','inkscape'): 'Annotation',
                       'style': simplestyle.formatStyle(line_style),
                       'x': str(position[0]),
                       'y': str((position[1] + text_height) * 1.2)
                       }
        line = inkex.etree.SubElement(node, inkex.addNS('text','svg'), line_attribs)
        line.text = text

           
    def calc_unit_factor(self):
        """ given the document units and units declared in this extension's 
            dialog - return the scale factor for all dimension conversions
        """
        # namedView = self.document.getroot().find(inkex.addNS('namedview', 'sodipodi'))
        # doc_units = inkex.uutounit(1.0, namedView.get(inkex.addNS('document-units', 'inkscape')))
        dialog_units = inkex.uutounit(1.0, self.options.units)
        unit_factor = 1.0/dialog_units
        dimension = self.options.dimension
        # print >> self.tty, "unit_factor=%s, doc_units=%s, dialog_units=%s (%s), system=%s" % (unit_factor, doc_units, dialog_units, self.options.units, self.options.system)
        if   self.options.system == 'CP': # circular pitch
            circular_pitch = dimension
        elif self.options.system == 'DP': # diametral pitch 
                circular_pitch = pi / dimension
        elif self.options.system == 'MM': # module (metric)
            circular_pitch = dimension * pi / 25.4
        else:
            inkex.debug("unknown system '%s', try CP, DP, MM" % self.options.system)
        # circular_pitch defines the size in inches.
        # We divide the internal inch factor (px = 90dpi), to remove the inch 
        # unit.
        # The internal inkscape unit is always px, 
        # it is independent of the doc_units!
        return unit_factor, circular_pitch / inkex.uutounit(1.0, 'in')
        

    def effect(self):
        """ Calculate Gear factors from inputs.
            - Make list of radii, angles, and centers for each tooth and 
              iterate through them
            - Turn on other visual features e.g. cross, rack, annotations, etc
        """
        path_stroke = '#000000'  # might expose one day
        path_fill   = 'none'     # no fill - just a line
        path_stroke_width  = 0.6 			# might expose one day
        path_stroke_light  = path_stroke_width * 0.25 	# guides are thinner
        
        # Debug using:  inkex.debug( "angle=%s pitch=%s" % (angle, pitch) )
        # take into account document dimensions and units in dialog. 
        unit_factor,pitch = self.calc_unit_factor()
        teeth = self.options.teeth
	# Angle of tangent to tooth at circular pitch wrt radial line.
        angle = self.options.angle 
        # Clearance: Radial distance between top of tooth on one gear to 
	# bottom of gap on another.
        clearance = self.options.clearance * unit_factor
        
        accuracy_involute = 20 # Number of points of the involute curve
        accuracy_circular = 9  # Number of points on circular parts
        if self.options.accuracy is not None:
            if self.options.accuracy == 0:  
                # automatic
                if   teeth < 10: accuracy_involute = 20
                elif teeth < 30: accuracy_involute = 12
                else:            accuracy_involute = 6
            else:
                accuracy_involute = self.options.accuracy
            accuracy_circular = max(3, int(accuracy_involute/2) - 1) # never less than three
        # print >>self.tty, "accuracy_circular=%s accuracy_involute=%s" % (accuracy_circular, accuracy_involute)

        
        mount_hole = self.options.mount_hole * unit_factor
        mount_radius = self.options.mount_diameter * 0.5 * unit_factor

        spoke_count = self.options.spoke_count
        holes_rounding = self.options.holes_rounding * unit_factor
        spoke_width = self.options.spoke_width * unit_factor
        
        # should we combine to draw_guides ?
        centercross = self.options.centercross # draw center or not (boolean)
        pitchcircle = self.options.pitchcircle # draw pitch circle or not (boolean)
        
        # print >>sys.stderr, "Teeth: %s\n"     % teeth
        two_pi = 2.0 * pi

        # Hopefully replace a lot of these with a call to a modified gear_calculations() above
        
        # Pitch (circular pitch): Length of the arc from one tooth to the next)
        # Pitch diameter: Diameter of pitch circle.
        pitch_diameter = teeth * pitch / pi
        pitch_radius   = pitch_diameter / 2.0

        # Base Circle
        base_diameter = pitch_diameter * cos( radians( angle ) )
        base_radius   = base_diameter / 2.0

        # Diametrial pitch: Number of teeth per unit length.
        pitch_diametrial = teeth / pitch_diameter

        # Addendum: Radial distance from pitch circle to outside circle.
        addendum = 1.0 / pitch_diametrial

        # Outer Circle
        outer_radius = pitch_radius + addendum
        outer_diameter = outer_radius * 2.0

        # Tooth thickness: Tooth width along pitch circle.
        tooth  = ( pi * pitch_diameter ) / ( 2.0 * teeth )

        # Undercut?
        undercut = int(ceil(undercut_min_teeth( angle )))
        needs_undercut = teeth < undercut

	if have_undercut(teeth, angle, 1.0):
	    min_teeth = int(ceil(undercut_min_teeth(angle, 1.0)))
	    min_angle = undercut_min_angle(teeth, 1.0) + .1
	    max_k = undercut_max_k(teeth, angle)
	    inkex.debug("Undercut Warning: This gear will not work well. Try tooth count of %d or more, or a pressure angle of %.1f ° or more, or try a profile shift of %d %% (not yet implemented). Or other decent combinations." % (min_teeth, min_angle, int(100.*max_k)-100.))

        # Dedendum: Radial distance from pitch circle to root diameter.
        dedendum = addendum + clearance

        # Root diameter: Diameter of bottom of tooth spaces. 
        root_radius =  pitch_radius - dedendum
        root_diameter = root_radius * 2.0

        # attempt at using base_calc function but scale errors
##        (pitch_radius, base_radius,
##        addendum, dedendum,
##        outer_radius, root_radius,
##        tooth) = gear_calculations(teeth, use_metric_module, self.options.module, pitch, angle, clearance)
##        inkex.debug(tooth)
        # All base calcs done. Start building gear
        
        half_thick_angle = two_pi / (4.0 * teeth ) #?? = pi / (2.0 * teeth)
        pitch_to_base_angle  = involute_intersect_angle( base_radius, pitch_radius )
        pitch_to_outer_angle = involute_intersect_angle( base_radius, outer_radius ) - pitch_to_base_angle

        start_involute_radius = max(base_radius, root_radius)
        radii = linspace(start_involute_radius, outer_radius, accuracy_involute)
        angles = [involute_intersect_angle(base_radius, r) for r in radii]

        centers = [(x * two_pi / float( teeth) ) for x in range( teeth ) ]
        points = []

        for c in centers:
            # Angles
            pitch1 = c - half_thick_angle
            base1  = pitch1 - pitch_to_base_angle
            offsetangles1 = [ base1 + x for x in angles]
            points1 = [ point_on_circle( radii[i], offsetangles1[i]) for i in range(0,len(radii)) ]

            pitch2 = c + half_thick_angle
            base2  = pitch2 + pitch_to_base_angle
            offsetangles2 = [ base2 - x for x in angles] 
            points2 = [ point_on_circle( radii[i], offsetangles2[i]) for i in range(0,len(radii)) ]

            points_on_outer_radius = [ point_on_circle(outer_radius, x) for x in linspace(offsetangles1[-1], offsetangles2[-1], accuracy_circular) ]

            if root_radius > base_radius:
                pitch_to_root_angle = pitch_to_base_angle - involute_intersect_angle(base_radius, root_radius )
                root1 = pitch1 - pitch_to_root_angle
                root2 = pitch2 + pitch_to_root_angle
                points_on_root = [point_on_circle (root_radius, x) for x in linspace(root2, root1+(two_pi/float(teeth)), accuracy_circular) ]
                p_tmp = points1 + points_on_outer_radius[1:-1] + points2[::-1] + points_on_root[1:-1] # [::-1] reverses list; [1:-1] removes first and last element
            else:
                points_on_root = [point_on_circle (root_radius, x) for x in linspace(base2, base1+(two_pi/float(teeth)), accuracy_circular) ]
                p_tmp = points1 + points_on_outer_radius[1:-1] + points2[::-1] + points_on_root # [::-1] reverses list

            points.extend( p_tmp )

        path = points_to_svgd( points )
        bbox_center = points_to_bbox_center( points )
        # print >>self.tty, bbox_center

        # Spokes
	if not self.options.spur_ring:	# only draw internals if spur gear
            holes = ''
            r_outer = root_radius - spoke_width
            for i in range(spoke_count):
                points = []
                start_a, end_a = i * two_pi / spoke_count, (i+1) * two_pi / spoke_count
                # inner circle around mount
                # - a better way to do this might be to increase local spoke width to be larger by epsilon than mount radius
                # - this soln prevents blowout but does not make a useful result.
                # Also mount radius should increase to avoid folding over when spoke_width gets big. But by what factor ?
                # - can we calc when spoke_count*(spoke_width+delta) exceeds circumference of mount_radius circle.
                # - then increase radius to fit - then recalc mount_radius.
                asin_factor = spoke_width/mount_radius/2
                # check if need to clamp radius
                if asin_factor > 1 : asin_factor = 1
                #a = asin(spoke_width/mount_radius/2)
                a = asin(asin_factor)
                points += [ point_on_circle(mount_radius, start_a + a), point_on_circle(mount_radius, end_a - a)]
                # outer circle near gear
##              try:
##                  a = asin(spoke_width/r_outer/2)
##              except:
##                  print >> sys.stderr, "error: Spoke width is too large:", spoke_width/unit_factor, "max=", r_outer*2/unit_factor
                
                # a better way to do this might be to decrease local spoke width to be smaller by epsilon than r_outer
                # this soln prevents blowout but does not make a useful result. (see above)
                asin_factor = spoke_width/r_outer/2
                # check if need to clamp radius
                if asin_factor > 1 : asin_factor = 1
                a = asin(asin_factor)
                points += [point_on_circle(r_outer, end_a - a), point_on_circle(r_outer, start_a + a) ]

                path += (
                        "M %f,%f" % points[0] +
                        "A  %f,%f %s %s %s %f,%f" % tuple((mount_radius, mount_radius, 0, 0 if spoke_count!=1 else 1, 1 ) + points[1]) +
                        "L %f,%f" % points[2] +
                        "A  %f,%f %s %s %s %f,%f" % tuple((r_outer, r_outer, 0, 0 if spoke_count!=1 else 1, 0 ) + points[3]) +
                        "Z"
                        )

            # Draw mount hole
            # A : rx,ry  x-axis-rotation, large-arch-flag, sweepflag  x,y
            r = mount_hole / 2
            path += (
                    "M %f,%f" % (0,r) +
                    "A  %f,%f %s %s %s %f,%f" % (r,r, 0,0,0, 0,-r) +
                    "A  %f,%f %s %s %s %f,%f" % (r,r, 0,0,0, 0,r) 
                    )
        else:
	    # its a ring gear
	    # which only has an outer ring where width = spoke width
	    r = outer_radius + spoke_width
            path += (
                    "M %f,%f" % (0,r) +
                    "A  %f,%f %s %s %s %f,%f" % (r,r, 0,0,0, 0,-r) +
                    "A  %f,%f %s %s %s %f,%f" % (r,r, 0,0,0, 0,r) 
                    )
        
        # Embed gear in group to make animation easier:
        #  Translate group, Rotate path.
        t = 'translate(' + str( self.view_center[0] ) + ',' + str( self.view_center[1] ) + ')'
        g_attribs = { inkex.addNS('label','inkscape'):'Gear' + str( teeth ),
                      inkex.addNS('transform-center-x','inkscape'): str(-bbox_center[0]),
                      inkex.addNS('transform-center-y','inkscape'): str(-bbox_center[1]),
                      'transform':t,
                      'info':'N:'+str(teeth)+'; Pitch:'+ str(pitch) + '; Pressure Angle: '+str(angle) }
        # add the group to the current layer
        g = inkex.etree.SubElement(self.current_layer, 'g', g_attribs )

        # Create SVG Path for gear under top level group
        style = { 'stroke': path_stroke, 'fill': path_fill, 'stroke-width': path_stroke_width }
        gear_attribs = { 'style': simplestyle.formatStyle(style), 'd': path }
        gear = inkex.etree.SubElement(g, inkex.addNS('path','svg'), gear_attribs )

        # Add center
        if centercross:
            style = { 'stroke': path_stroke, 'fill': path_fill, 'stroke-width': path_stroke_light }
            cs = str(pitch / 3) # centercross length
            d = 'M-'+cs+',0L'+cs+',0M0,-'+cs+'L0,'+cs  # 'M-10,0L10,0M0,-10L0,10'
            center_attribs = { inkex.addNS('label','inkscape'): 'Center cross',
                               'style': simplestyle.formatStyle(style), 'd': d }
            center = inkex.etree.SubElement(g, inkex.addNS('path','svg'), center_attribs )

        # Add pitch circle (for mating)
        if pitchcircle:
            style = { 'stroke': path_stroke, 'fill': path_fill, 'stroke-width': path_stroke_light }
            draw_SVG_circle(g, pitch_radius, 0, 0, 'Pitch circle', style)

        # Add Rack (below)
        if self.options.drawrack:
            base_height = self.options.base_height * unit_factor
            tab_width = self.options.base_tab * unit_factor
            tooth_count = self.options.teeth_length
            (path,path2) = generate_rack_path(tooth_count, pitch, addendum, angle,
                                      base_height, tab_width, clearance, pitchcircle)
            # position below Gear, so that it meshes nicely
	    # xoff = 0			## if teeth % 4 == 2.
	    # xoff = -0.5*pitch		## if teeth % 4 == 0.
	    # xoff = -0.75*pitch 	## if teeth % 4 == 3.
	    # xoff = -0.25*pitch	## if teeth % 4 == 1.
	    xoff = (-0.5, -0.25, 0, -0.75)[teeth % 4] * pitch
            t = 'translate(' + str( xoff ) + ',' + str( pitch_radius ) + ')'
            g_attribs = { inkex.addNS('label', 'inkscape'): 'RackGear' + str(tooth_count),
                          'transform': t }
            rack = inkex.etree.SubElement(g, 'g', g_attribs)

            # Create SVG Path for gear
            style = {'stroke': path_stroke, 'fill': 'none', 'stroke-width': path_stroke_width }
            gear_attribs = { 'style': simplestyle.formatStyle(style), 'd': path }
            gear = inkex.etree.SubElement(
                rack, inkex.addNS('path', 'svg'), gear_attribs)
            if path2 is not None:
                style2 = { 'stroke': path_stroke, 'fill': 'none', 'stroke-width': path_stroke_light }
                gear_attribs2 = { 'style': simplestyle.formatStyle(style2), 'd': path2 }
                gear = inkex.etree.SubElement(
                    rack, inkex.addNS('path', 'svg'), gear_attribs2)


        # Add Annotations (above)
        if self.options.annotation:
	    outer_dia = outer_diameter
	    if self.options.spur_ring:
		outer_dia += 2 * spoke_width
            notes =[#'Document (%s) scale conversion = %2.4f' % (self.document.getroot().find(inkex.addNS('namedview', 'sodipodi')).get(inkex.addNS('document-units', 'inkscape')),
                    #                                            unit_factor),
                    'Teeth: %d   CP: %2.4f(%s) ' % (teeth, pitch / unit_factor, self.options.units),
                    'DP: %2.4f Module: %2.4f' %(pi / pitch * unit_factor, pitch / pi * 25.4),
                    'Pressure Angle: %2.4f degrees' % (angle),
                    'Pitch diameter: %2.4f %s' % (pitch_diameter / unit_factor, self.options.units),
                    'Outer diameter: %2.4f %s' % (outer_dia / unit_factor, self.options.units),
                    'Base diameter:  %2.4f %s' % (base_diameter / unit_factor, self.options.units)#,
                    #'Addendum:      %2.4f %s'  % (addendum / unit_factor, self.options.units),
                    #'Dedendum:      %2.4f %s'  % (dedendum / unit_factor, self.options.units)
                    ]
            text_height = 22
            # position above
            y = - outer_radius - (len(notes)+1) * text_height * 1.2
            for note in notes:
                self.add_text(g, note, [0,y], text_height)
                y += text_height * 1.2

if __name__ == '__main__':
    e = Gears()
    e.affect()

# Notes

