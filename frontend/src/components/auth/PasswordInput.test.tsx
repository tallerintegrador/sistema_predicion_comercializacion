import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PasswordInput } from './PasswordInput'

describe('PasswordInput', () => {
  it('alterna entre mostrar y ocultar la contraseña', () => {
    const { container } = render(<PasswordInput id="p" value="secreto" onChange={() => {}} />)
    const input = container.querySelector('#p') as HTMLInputElement

    expect(input.type).toBe('password')
    fireEvent.click(screen.getByRole('button', { name: 'Mostrar contraseña' }))
    expect(input.type).toBe('text')
    fireEvent.click(screen.getByRole('button', { name: 'Ocultar contraseña' }))
    expect(input.type).toBe('password')
  })
})
