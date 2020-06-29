# -*- coding:utf-8 -*-
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GLUT import *

dX = 0.0
dY = 0.0
alphaX = 0.0
alphaY = 0.0
alphaZ = 0.0
sf = 0.0


def init():
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    glOrtho(-4.0 * 64 / 48.0, 4.0 * 64 / 48, -4.0, 4.0, 0.0, 10)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    gluLookAt(4.0, 2.0, 4.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    glViewport(0, 0, 640, 480)


def axis(length):
    glPushMatrix()
    glBegin(GL_LINES)
    glVertex3d(0, 0, 0)
    glVertex3d(0, 0, length)
    glEnd()
    glTranslated(0, 0, length - 0.2)
    glutWireCone(0.04, 0.2, 12, 9)
    glPopMatrix()


def displayWire():
    glClear(GL_COLOR_BUFFER_BIT)
    glClearColor(0.0, 0.0, 0.0, 0.0)
    glPushMatrix()
    glTranslated(0.0, 0.0, 0.0)
    glRotated(alphaY, 0.0, 1.0, 0.0)
    glRotated(alphaX, 1.0, 0.0, 0.0)
    glRotated(alphaZ, 0.0, 0.0, 1.0)
    glTranslated(dY, 0.0, 1.0)
    glTranslated(dX, 1.0, 0.0)
    glPushMatrix()
    glColor3d(0.0, 0.0, 1.0)
    axis(2.0)
    glRasterPos3f(0.0, 0.0, 2.3)

    glRotated(-90, 1.0, 0.0, 0.0)
    glColor3d(0.0, 1.0, 0.0)
    axis(2.0)
    glRasterPos3f(0.0, 0.0, 2.3)

    glColor3d(1.0, 0.0, 0.0)
    glRotated(90, 0.0, 1.0, 0.0)
    axis(2.0)
    glRasterPos3f(0.0, 0.0, 2.3)
    glPopMatrix()

    glColor3d(1.0, 1.0, 0.0)
    glScaled(1.5, 1.5, 1.5)


    glPushMatrix()
    glColor3d(1.0, 1.0, 1.0)
    glTranslated(0.0, 1.5, 0.0)
    glScaled(1 + sf, 1 + sf, 1 + sf)

    glRotated(360, 0, 1, 0)
    glutWireSphere(0.35, 30, 30)
    glPopMatrix()

    glPushMatrix()
    glColor3d(1.0, 1.0, 0.0)
    glRotated(120, 0, 1, 0)
    glScaled(1 + sf, 1 + sf, 1 + sf)
    glTranslated(0.0, 0.5, 1.0)
    glutWireCube(0.35)
    glPopMatrix()

    glPushMatrix()
    glColor3d(0.0, 1.0, 1.0)
    glRotated(290, 0, 1, 0)
    glScaled(1 + sf, 1 + sf, 1 + sf)
    glTranslated(0.0, 0.5, 1.0)
    glutWireCube(0.35)
    glPopMatrix()

    glPushMatrix()
    glColor3d(1.0, 0.0, 1.0)
    glTranslated(0.0, 0.0, 0.0)
    glScaled(1 + sf, 1 + sf, 1 + sf)
    glRotated(-90.0, 1, 0, 0)
    qobj = gluNewQuadric()
    gluQuadricDrawStyle(qobj, GLU_LINE)
    gluCylinder(qobj, 0.50, 0.50, 0.80, 30, 30)
    glPopMatrix()
    glPopMatrix()
    glutSwapBuffers()

def mySpecialKey(key, x, y):
    if (key == GLUT_KEY_RIGHT):
        global alphaX
        alphaX += 5.0
    if (key == GLUT_KEY_LEFT):
        global alphaZ
        alphaZ -= 5.0
    if (key == GLUT_KEY_UP):
        global alphaY
        alphaY += 5.0
    if (key == GLUT_KEY_DOWN):
        global alphaY
        alphaY -= 5.0
    glutPostRedisplay()

def keyboard(key, x, y):
    if key == 'a':
        global dY
        dY += 0.5
    glutPostRedisplay()


if __name__ == '__main__':
    glutInit()
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGB)
    glutInitWindowSize(640, 640)
    glutInitWindowPosition(100, 100)
    glutCreateWindow("a")
    glutDisplayFunc(displayWire)
    glutSpecialFunc(mySpecialKey)
    glutKeyboardFunc(keyboard)
    init()
    glutMainLoop()
